import logging
import asyncio
import aiohttp
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pandas as pd
import numpy as np

API_KEY = "YOUR_TWELVEDATA_API_KEY"
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

user_data = {}

strategies = {
    "default": "ma_rsi_macd",
    "ma_rsi_macd": "MA + RSI + MACD",
    "boll_stoch": "Bollinger + Stochastic"
}

def main_keyboard(user_id):
    mute = user_data.get(user_id, {}).get("mute", False)
    mute_btn = "🔔 Unmute" if mute else "🔕 Mute"
    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🔄 Получить сигнал", callback_data="get_signal"),
        InlineKeyboardButton("BTCUSD", callback_data="set_BTCUSD"),
        InlineKeyboardButton("XAUUSD", callback_data="set_XAUUSD"),
        InlineKeyboardButton("EURUSD", callback_data="set_EURUSD"),
        InlineKeyboardButton(mute_btn, callback_data="toggle_mute"),
        InlineKeyboardButton("🎯 Стратегия", callback_data="choose_strategy"),
        InlineKeyboardButton("🕒 Расписание", callback_data="schedule"),
        InlineKeyboardButton("📊 Статус", callback_data="status")
    )

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {
            "asset": "BTC/USD",
            "mute": False,
            "strategy": "ma_rsi_macd",
            "schedule": {}
        }
    await message.answer("💊 Пора выбраться из матрицы", reply_markup=main_keyboard(user_id))

@dp.callback_query_handler(lambda c: c.data == "toggle_mute")
async def toggle_mute(call: types.CallbackQuery):
    user_id = call.from_user.id
    user_data[user_id]["mute"] = not user_data[user_id].get("mute", False)
    await call.message.edit_reply_markup(reply_markup=main_keyboard(user_id))

@dp.callback_query_handler(lambda c: c.data.startswith("set_"))
async def set_asset(call: types.CallbackQuery):
    user_id = call.from_user.id
    asset_map = {
        "set_BTCUSD": "BTC/USD",
        "set_XAUUSD": "XAU/USD",
        "set_EURUSD": "EUR/USD"
    }
    user_data[user_id]["asset"] = asset_map[call.data]
    await call.answer(f"✅ Актив выбран: {asset_map[call.data]}")

@dp.callback_query_handler(lambda c: c.data == "status")
async def status(call: types.CallbackQuery):
    user_id = call.from_user.id
    data = user_data[user_id]
    await call.message.answer(
        f"📊 Ваши настройки:\n"
        f"Актив: {data['asset']}\n"
        f"Стратегия: {strategies.get(data['strategy'], 'не выбрана')}\n"
        f"Mute: {'On' if data['mute'] else 'Off'}"
    )

@dp.callback_query_handler(lambda c: c.data == "choose_strategy")
async def choose_strategy(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=1)
    for key, name in strategies.items():
        if key != "default":
            kb.add(InlineKeyboardButton(name, callback_data=f"strategy_{key}"))
    await call.message.answer("Выберите стратегию:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("strategy_"))
async def set_strategy(call: types.CallbackQuery):
    strategy_key = call.data.split("_")[1]
    user_id = call.from_user.id
    user_data[user_id]["strategy"] = strategy_key
    await call.answer(f"✅ Стратегия выбрана: {strategies[strategy_key]}")

@dp.callback_query_handler(lambda c: c.data == "get_signal")
async def get_signal(call: types.CallbackQuery):
    user_id = call.from_user.id
    asset = user_data[user_id]["asset"]
    strategy = user_data[user_id]["strategy"]
    result = await analyze_asset(asset, strategy)
    await call.message.answer(result)

async def analyze_asset(asset, strategy):
    symbol = asset.replace("/", "")
    interval = "15min"
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=200&apikey={API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            raw = await resp.json()

    if "values" not in raw:
        return "⚠️ Ошибка загрузки данных"

    df = pd.DataFrame(raw["values"])
    df = df.iloc[::-1]
    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)

    if strategy == "ma_rsi_macd":
        signal, confidence = ma_rsi_macd(df)
    else:
        signal, confidence = boll_stoch(df)

    if confidence < 60:
        return f"⚠️ Риск велик, не время торговли (точность: {confidence:.1f}%)"
    if signal == "Hold":
        return f"🤖 Нет сигнала (точность: {confidence:.1f}%)"

    price = df['close'].iloc[-1]
    tp = price * (1.03 if signal == "Buy" else 0.97)
    sl = price * (0.97 if signal == "Buy" else 1.03)

    return (
        f"📈 Сигнал по {asset}\n"
        f"Направление: {signal}\n"
        f"Цена входа: {price:.2f}\n"
        f"🎯 Take-Profit: {tp:.2f}\n"
        f"🛑 Stop-Loss: {sl:.2f}\n"
        f"🎯 Точность прогноза: {confidence:.1f}%"
    )

# === STRATEGIES ===

def ma_rsi_macd(df):
    close = df['close']

    ma10 = close.rolling(window=10).mean()
    ma50 = close.rolling(window=50).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26

    buy = ma10.iloc[-1] > ma50.iloc[-1] and rsi.iloc[-1] < 70 and macd.iloc[-1] > 0
    sell = ma10.iloc[-1] < ma50.iloc[-1] and rsi.iloc[-1] > 30 and macd.iloc[-1] < 0

    confidence = 80 if buy or sell else 50
    signal = "Buy" if buy else "Sell" if sell else "Hold"
    return signal, confidence

def boll_stoch(df):
    close = df['close']
    high = df['high']
    low = df['low']

    mid = close.rolling(window=20).mean()
    std = close.rolling(window=20).std()
    upper = mid + 2 * std
    lower = mid - 2 * std

    low_14 = low.rolling(window=14).min()
    high_14 = high.rolling(window=14).max()
    stoch_k = 100 * ((close - low_14) / (high_14 - low_14))

    buy = close.iloc[-1] < lower.iloc[-1] and stoch_k.iloc[-1] < 20
    sell = close.iloc[-1] > upper.iloc[-1] and stoch_k.iloc[-1] > 80

    confidence = 75 if buy or sell else 50
    signal = "Buy" if buy else "Sell" if sell else "Hold"
    return signal, confidence

# === SCHEDULER PLACEHOLDER ===
async def scheduler_start():
    scheduler.start()
    # можно настроить расписание для отправки автоматических сигналов

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler_start())
    executor.start_polling
