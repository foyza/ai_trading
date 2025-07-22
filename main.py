import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiosqlite
import httpx
import os

API_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
TWELVE_API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'

ASSETS = ['BTC/USD', 'XAU/USD', 'EUR/USD']
STRATEGIES = ['MA+RSI+MACD', 'Bollinger+Stochastic']
DEFAULT_STRATEGY = 'MA+RSI+MACD'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

# ---------- DATABASE ----------
async def init_db():
    async with aiosqlite.connect("users.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            asset TEXT DEFAULT 'BTC/USD',
            strategy TEXT DEFAULT ?,
            mute INTEGER DEFAULT 0
        )
        """, (DEFAULT_STRATEGY,))
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
    mute_status = "🔕 Mute" if user[3] == 0 else "🔔 Unmute"
    buttons = [
        [InlineKeyboardButton(text="🔄 Получить сигнал", callback_data="signal")],
        [InlineKeyboardButton(text="BTCUSD", callback_data="asset_BTC/USD"),
         InlineKeyboardButton(text="XAUUSD", callback_data="asset_XAU/USD"),
         InlineKeyboardButton(text="EURUSD", callback_data="asset_EUR/USD")],
        [InlineKeyboardButton(text=mute_status, callback_data="toggle_mute")],
        [InlineKeyboardButton(text="🎯 Стратегия", callback_data="strategy")],
        [InlineKeyboardButton(text="🕒 Расписание", callback_data="schedule")],
        [InlineKeyboardButton(text="📊 Статус", callback_data="status")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- MARKET ANALYSIS ----------
async def fetch_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=50&apikey={TWELVE_API_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        data = r.json()
        return data["values"]

def mock_signal(data, strategy):
    # 🔧 Replace with real indicators: MA, RSI, MACD, etc.
    import random
    confidence = random.randint(50, 90)
    if confidence >= 70:
        return {
            "direction": "Buy" if random.random() > 0.5 else "Sell",
            "entry": float(data[0]["close"]),
            "take_profit": round(float(data[0]["close"]) * 1.02, 2),
            "stop_loss": round(float(data[0]["close"]) * 0.98, 2),
            "confidence": confidence
        }
    elif confidence < 60:
        return {"warning": f"⚠️ Риск велик, не время торговли (точность: {confidence}%)"}
    else:
        return None

# ---------- HANDLERS ----------
@dp.message(commands=["start"])
async def start_handler(message: types.Message):
    await get_user(message.from_user.id)
    await message.answer("👋 Пора выбраться из матрицы", reply_markup=main_menu(await get_user(message.from_user.id)))

@dp.callback_query()
async def callback_handler(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)

    if call.data == "signal":
        data = await fetch_data(user[1])
        signal = mock_signal(data, user[2])
        if not signal:
            await call.message.answer("Нет уверенного сигнала.")
        elif "warning" in signal:
            await call.message.answer(signal["warning"])
        else:
            await call.message.answer(
                f"🎯 Сигнал по {user[1]}\n📈 {signal['direction']}\nЦена входа: {signal['entry']}\n"
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
        status = "🔕 Оповещения отключены" if new_mute else "🔔 Оповещения включены"
        await call.message.answer(status)

    elif call.data == "strategy":
        builder = InlineKeyboardBuilder()
        for strat in STRATEGIES:
            builder.button(text=strat, callback_data=f"strat_{strat}")
        builder.adjust(1)
        await call.message.answer("Выберите стратегию:", reply_markup=builder.as_markup())

    elif call.data.startswith("strat_"):
        strat = call.data.split("_")[1]
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
