import asyncio
import logging
import os
import httpx
import aiosqlite
import numpy as np
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# API keys from environment variables (best for Railway)
API_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
TWELVE_API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

ASSETS = ['BTC/USD', 'XAU/USD', 'EUR/USD']
STRATEGIES = ['MA+RSI+MACD', 'Bollinger+Stochastic']

# ---------- DATABASE ----------
async def init_db():
    async with aiosqlite.connect("users.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            asset TEXT DEFAULT 'BTC/USD',
            strategy TEXT DEFAULT 'MA+RSI+MACD',
            mute INTEGER DEFAULT 0
        )""")
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            if not user:
                await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                await db.commit()
                return await get_user(user_id)
            return user

async def update_user(user_id, field, value):
    async with aiosqlite.connect("users.db") as db:
        await db.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

# ---------- UI ----------
def main_menu(user):
    mute_btn = "🔕 Mute" if user[3] == 0 else "🔔 Unmute"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Получить сигнал", callback_data="signal")],
        [InlineKeyboardButton(text="BTCUSD", callback_data="asset_BTC/USD"),
         InlineKeyboardButton(text="XAUUSD", callback_data="asset_XAU/USD"),
         InlineKeyboardButton(text="EURUSD", callback_data="asset_EUR/USD")],
        [InlineKeyboardButton(text=mute_btn, callback_data="toggle_mute")],
        [InlineKeyboardButton(text="🎯 Стратегия", callback_data="strategy")],
        [InlineKeyboardButton(text="🕒 Расписание", callback_data="schedule")],
        [InlineKeyboardButton(text="📊 Статус", callback_data="status")]
    ])

# ---------- STRATEGIES ----------
def calculate_indicators(df, strategy):
    df["close"] = df["close"].astype(float)

    if strategy == "MA+RSI+MACD":
        df["MA10"] = df["close"].rolling(window=10).mean()
        df["MA50"] = df["close"].rolling(window=50).mean()
        delta = df["close"].diff()
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = pd.Series(gain).rolling(window=14).mean()
        avg_loss = pd.Series(loss).rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df["RSI"] = 100 - (100 / (1 + rs))
        df["EMA12"] = df["close"].ewm(span=12).mean()
        df["EMA26"] = df["close"].ewm(span=26).mean()
        df["MACD"] = df["EMA12"] - df["EMA26"]

        last = df.iloc[-1]
        direction = None
        if last["MA10"] > last["MA50"] and last["RSI"] > 50 and last["MACD"] > 0:
            direction = "Buy"
        elif last["MA10"] < last["MA50"] and last["RSI"] < 50 and last["MACD"] < 0:
            direction = "Sell"
        return direction

    elif strategy == "Bollinger+Stochastic":
        df["MA20"] = df["close"].rolling(window=20).mean()
        df["STD20"] = df["close"].rolling(window=20).std()
        df["Upper"] = df["MA20"] + 2 * df["STD20"]
        df["Lower"] = df["MA20"] - 2 * df["STD20"]
        df["%K"] = ((df["close"] - df["close"].rolling(14).min()) /
                   (df["close"].rolling(14).max() - df["close"].rolling(14).min())) * 100
        df["%D"] = df["%K"].rolling(3).mean()

        last = df.iloc[-1]
        direction = None
        if last["close"] < last["Lower"] and last["%K"] < 20:
            direction = "Buy"
        elif last["close"] > last["Upper"] and last["%K"] > 80:
            direction = "Sell"
        return direction
    return None

async def fetch_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=50&apikey={TWELVE_API_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        raw = r.json()
        df = pd.DataFrame(raw["values"])[::-1]  # reverse for ascending order
        df["close"] = df["close"].astype(float)
        return df

async def generate_signal(asset, strategy):
    df = await fetch_data(asset)
    direction = calculate_indicators(df, strategy)

    if direction:
        entry = df.iloc[-1]["close"]
        confidence = 75  # placeholder, in real app — calculate from backtest stats
        return {
            "direction": direction,
            "entry": entry,
            "take_profit": round(entry * 1.02, 2),
            "stop_loss": round(entry * 0.98, 2),
            "confidence": confidence
        }
    else:
        return {"warning": "⚠️ Риск велик, не время торговли (точность: <60%)"}

# ---------- HANDLERS ----------
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await get_user(message.from_user.id)
    await message.answer("Пора выбраться из матрицы", reply_markup=main_menu(await get_user(message.from_user.id)))

@dp.callback_query()
async def callback_handler(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)

    if call.data == "signal":
        signal = await generate_signal(user[1], user[2])
        if "warning" in signal:
            await call.message.answer(signal["warning"])
        else:
            await call.message.answer(
                f"🎯 Сигнал по {user[1]}\n📈 {signal['direction']}\n"
                f"Цена входа: {signal['entry']}\n"
                f"TP: {signal['take_profit']} | SL: {signal['stop_loss']}\n"
                f"Точность: {signal['confidence']}%"
            )

    elif call.data.startswith("asset_"):
        asset = call.data.split("_")[1]
        await update_user(call.from_user.id, "asset", asset)
        await call.message.answer(f"✅ Актив установлен: {asset}")

    elif call.data == "toggle_mute":
        new_mute = 0 if user[3] == 1 else 1
        await update_user(call.from_user.id, "mute", new_mute)
        await call.message.answer("🔕 Оповещения отключены" if new_mute else "🔔 Оповещения включены")

    elif call.data == "strategy":
        builder = InlineKeyboardBuilder()
        for strat in STRATEGIES:
            builder.button(text=strat, callback_data=f"strat_{strat}")
        builder.adjust(1)
        await call.message.answer("Выберите стратегию:", reply_markup=builder.as_markup())

    elif call.data.startswith("strat_"):
        strat = call.data.split("_", 1)[1]
        await update_user(call.from_user.id, "strategy", strat)
        await call.message.answer(f"✅ Стратегия установлена: {strat}")

    elif call.data == "status":
        mute_text = "🔕 Mute" if user[3] else "🔔 Unmute"
        await call.message.answer(
            f"📊 Ваши настройки:\nАктив: {user[1]}\nСтратегия: {user[2]}\nMute: {mute_text}"
        )

    elif call.data == "schedule":
        await call.message.answer("🕒 Настройка расписания пока в разработке.")

    await call.answer()

# ---------- ENTRY POINT ----------
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
