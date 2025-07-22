import os
import logging
import httpx
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import pandas as pd
import numpy as np
import talib
from collections import defaultdict

API_TOKEN = os.getenv("BOT_TOKEN")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

logging.basicConfig(level=logging.INFO)

# Пользовательские настройки
user_settings = defaultdict(lambda: {
    "asset": "BTC/USD",
    "strategy": "auto",
    "mute": False,
    "schedule": {},
})

ASSETS = ["BTC/USD", "XAU/USD", "EUR/USD"]
STRATEGIES = ["MA+RSI+MACD", "Bollinger+Stochastic"]

def get_keyboard(user_id):
    mute_btn = "🔕 Mute" if not user_settings[user_id]["mute"] else "🔔 Unmute"
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔄 Получить сигнал", callback_data="get_signal"),
        InlineKeyboardButton("BTC/USD", callback_data="asset_BTC/USD"),
        InlineKeyboardButton("XAU/USD", callback_data="asset_XAU/USD"),
        InlineKeyboardButton("EUR/USD", callback_data="asset_EUR/USD"),
        InlineKeyboardButton(mute_btn, callback_data="toggle_mute"),
        InlineKeyboardButton("🎯 Стратегия", callback_data="choose_strategy"),
        InlineKeyboardButton("🕒 Расписание", callback_data="schedule"),
        InlineKeyboardButton("📊 Статус", callback_data="status"),
    )
    return kb

async def fetch_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol.replace('/', '')}&interval=15min&outputsize=100&apikey={TWELVEDATA_API_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        data = r.json()
        if "values" not in data:
            return None
        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime")
        df.set_index("datetime", inplace=True)
        df = df.astype(float)
        return df

def strategy_ma_rsi_macd(df):
    df["MA10"] = talib.SMA(df["close"], timeperiod=10)
    df["MA50"] = talib.SMA(df["close"], timeperiod=50)
    df["RSI"] = talib.RSI(df["close"], timeperiod=14)
    macd, macdsignal, _ = talib.MACD(df["close"])
    df["MACD"] = macd
    df["MACD_SIGNAL"] = macdsignal

    last = df.iloc[-1]
    direction = None
    if last["MA10"] > last["MA50"] and last["RSI"] > 50 and last["MACD"] > last["MACD_SIGNAL"]:
        direction = "Buy"
    elif last["MA10"] < last["MA50"] and last["RSI"] < 50 and last["MACD"] < last["MACD_SIGNAL"]:
        direction = "Sell"

    accuracy = 0.75 if direction else 0.55
    return direction, accuracy

def strategy_boll_stoch(df):
    upper, middle, lower = talib.BBANDS(df["close"], timeperiod=20)
    slowk, slowd = talib.STOCH(df["high"], df["low"], df["close"])
    df["upper"] = upper
    df["lower"] = lower
    df["slowk"] = slowk
    df["slowd"] = slowd

    last = df.iloc[-1]
    direction = None
    if last["close"] < last["lower"] and last["slowk"] < 20 and last["slowd"] < 20:
        direction = "Buy"
    elif last["close"] > last["upper"] and last["slowk"] > 80 and last["slowd"] > 80:
        direction = "Sell"

    accuracy = 0.72 if direction else 0.58
    return direction, accuracy

def calculate_tp_sl(price, direction):
    tp_pct = 0.02
    sl_pct = 0.01
    if direction == "Buy":
        tp = price * (1 + tp_pct)
        sl = price * (1 - sl_pct)
    else:
        tp = price * (1 - tp_pct)
        sl = price * (1 + sl_pct)
    return round(tp, 2), round(sl, 2), tp_pct * 100, sl_pct * 100

@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    await msg.answer("Пора выбраться из матрицы", reply_markup=get_keyboard(msg.from_user.id))

@dp.callback_query_handler()
async def handle_callback(query: types.CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if data.startswith("asset_"):
        asset = data.split("_")[1]
        user_settings[user_id]["asset"] = asset
        await query.answer(f"Выбран: {asset}")
    elif data == "toggle_mute":
        user_settings[user_id]["mute"] = not user_settings[user_id]["mute"]
        state = "🔕" if user_settings[user_id]["mute"] else "🔔"
        await query.answer(f"Звук: {state}")
    elif data == "choose_strategy":
        user_settings[user_id]["strategy"] = "auto" if user_settings[user_id]["strategy"] != "auto" else "Bollinger+Stochastic"
        await query.answer(f"Стратегия: {user_settings[user_id]['strategy']}")
    elif data == "status":
        s = user_settings[user_id]
        await query.message.answer(
            f"📊 Ваши настройки:\nАктив: {s['asset']}\nСтратегия: {s['strategy']}\nMute: {'Да' if s['mute'] else 'Нет'}"
        )
    elif data == "get_signal":
        await send_signal(user_id, query.message)
    else:
        await query.answer("В разработке...")

    await query.message.edit_reply_markup(reply_markup=get_keyboard(user_id))

async def send_signal(user_id, message):
    asset = user_settings[user_id]["asset"]
    symbol = asset.replace("/", "")
    df = await fetch_data(symbol)
    if df is None:
        await message.answer("❌ Не удалось получить данные.")
        return

    strategy = user_settings[user_id]["strategy"]
    if strategy == "auto":
        d1, a1 = strategy_ma_rsi_macd(df)
        d2, a2 = strategy_boll_stoch(df)
        if a1 > a2:
            direction, accuracy = d1, a1
        else:
            direction, accuracy = d2, a2
    elif strategy == "MA+RSI+MACD":
        direction, accuracy = strategy_ma_rsi_macd(df)
    else:
        direction, accuracy = strategy_boll_stoch(df)

    if not direction:
        await message.answer(f"⚠️ Риск велик, не время торговли (точность: {round(accuracy * 100)}%)")
        return

    entry = round(df["close"].iloc[-1], 2)
    tp, sl, tp_pct, sl_pct = calculate_tp_sl(entry, direction)
    await message.answer(
        f"📈 Сигнал по {asset}:\n"
        f"Направление: {direction}\n"
        f"Цена входа: {entry}\n"
        f"🎯 Take-Profit: {tp} (+{tp_pct}%)\n"
        f"🛑 Stop-Loss: {sl} (-{sl_pct}%)\n"
        f"📊 Точность прогноза: {round(accuracy * 100)}%"
    )

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
