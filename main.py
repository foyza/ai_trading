import logging
import asyncio
import aiohttp
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pandas as pd
import talib

API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"
TELEGRAM_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

# user data: user_id -> settings
user_data = {}

# --- кнопки ---
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

strategies = {
    "default": "ma_rsi_macd",
    "ma_rsi_macd": "MA + RSI + MACD",
    "boll_stoch": "Bollinger + Stochastic"
}

# --- приветствие ---
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

# --- переключение mute ---
@dp.callback_query_handler(lambda c: c.data == "toggle_mute")
async def toggle_mute(call: types.CallbackQuery):
    user_id = call.from_user.id
    user_data[user_id]["mute"] = not user_data[user_id].get("mute", False)
    await call.message.edit_reply_markup(reply_markup=main_keyboard(user_id))

# --- выбор актива ---
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

# --- статус пользователя ---
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

# --- выбор стратегии ---
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

# --- получение сигнала ---
@dp.callback_query_handler(lambda c: c.data == "get_signal")
async def get_signal(call: types.CallbackQuery):
    user_id = call.from_user.id
    asset = user_data[user_id]["asset"]
    strategy = user_data[user_id]["strategy"]
    result = await analyze_asset(asset, strategy)
    await call.message.answer(result)

# --- анализ по стратегии ---
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
    df = df.iloc[::-1].astype(float)

    if strategy == "ma_rsi_macd":
        signal, confidence = ma_rsi_macd_strategy(df)
    else:
        signal, confidence = boll_stoch_strategy(df)

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

# --- стратегии ---
def ma_rsi_macd_strategy(df):
    ma10 = talib.MA(df['close'], timeperiod=10)
    ma50 = talib.MA(df['close'], timeperiod=50)
    rsi = talib.RSI(df['close'], timeperiod=14)
    macd, _, _ = talib.MACD(df['close'])

    buy = ma10.iloc[-1] > ma50.iloc[-1] and rsi.iloc[-1] < 70 and macd.iloc[-1] > 0
    sell = ma10.iloc[-1] < ma50.iloc[-1] and rsi.iloc[-1] > 30 and macd.iloc[-1] < 0

    confidence = 80 if buy or sell else 50
    signal = "Buy" if buy else "Sell" if sell else "Hold"
    return signal, confidence

def boll_stoch_strategy(df):
    upper, middle, lower = talib.BBANDS(df['close'])
    slowk, slowd = talib.STOCH(df['high'], df['low'], df['close'])
    buy = df['close'].iloc[-1] < lower.iloc[-1] and slowk.iloc[-1] < 20
    sell = df['close'].iloc[-1] > upper.iloc[-1] and slowk.iloc[-1] > 80

    confidence = 75 if buy or sell else 50
    signal = "Buy" if buy else "Sell" if sell else "Hold"
    return signal, confidence

# --- запуск планировщика ---
async def scheduler_start():
    scheduler.start()
    # Здесь можно добавить авто-сигналы по расписанию

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler_start())
    executor.start_polling(dp, skip_updates=True)
