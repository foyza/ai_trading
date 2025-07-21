import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

from datetime import datetime
import numpy as np

# === Настройки ===
API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVE_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

user_data = {}  # user_id: {asset, mute, strategy, schedule}


# === Кнопки ===
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Получить сигнал")],
            [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
            [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
            [KeyboardButton(text="🎯 Стратегия"), KeyboardButton(text="🕒 Расписание")],
            [KeyboardButton(text="📊 Статус")]
        ],
        resize_keyboard=True
    )


# === Обработка /start ===
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_data[user_id] = {
        "asset": "BTCUSD",
        "mute": False,
        "strategy": "default",
        "schedule": "24/7"
    }
    await message.answer("Пора выбраться из матрицы", reply_markup=main_keyboard())


# === Получение данных с TwelveData ===
async def get_price_data(asset: str):
    symbol_map = {
        "BTCUSD": "BTC/USD",
        "XAUUSD": "XAU/USD",
        "USTECH100": "NASDAQ100"  # ИСПРАВЛЕНИЕ: правильный символ
    }
    symbol = symbol_map.get(asset, "BTC/USD")

    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={symbol}&interval=1min&outputsize=100&apikey={TWELVE_API_KEY}"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            if "values" not in data or not data["values"]:
                return []
            return [float(bar["close"]) for bar in reversed(data["values"])]


# === Анализ стратегии ===
def analyze_strategy(closes):
    if len(closes) < 50:
        return None, 0

    ma10 = np.mean(closes[-10:])
    ma50 = np.mean(closes[-50:])
    rsi = 100 - 100 / (1 + (np.mean(np.diff(closes[-15:]) > 0)))
    macd = np.mean(closes[-12:]) - np.mean(closes[-26:])

    signals = [ma10 > ma50, rsi > 50, macd > 0]
    agree = sum(signals)

    if agree == 3:
        direction = "Buy" if ma10 > ma50 else "Sell"
        accuracy = 80
    elif agree == 2:
        direction = "Neutral"
        accuracy = 60
    else:
        direction = "None"
        accuracy = 40

    return direction, accuracy


# === Генерация сигнала ===
def generate_signal(direction, price):
    tp_pct, sl_pct = 0.015, 0.01
    if direction == "Buy":
        tp = price * (1 + tp_pct)
        sl = price * (1 - sl_pct)
    else:
        tp = price * (1 - tp_pct)
        sl = price * (1 + sl_pct)

    return f"""
📈 Сигнал: <b>{direction}</b>
🎯 Вход: <b>{price:.2f}</b>
✅ TP: <b>{tp:.2f}</b> (+{tp_pct*100:.1f}%)
❌ SL: <b>{sl:.2f}</b> (-{sl_pct*100:.1f}%)
"""


# === Обработка кнопок ===
@dp.message(F.text == "🔄 Получить сигнал")
async def manual_signal(message: types.Message):
    user_id = message.from_user.id
    data = user_data.get(user_id, {})
    asset = data.get("asset", "BTCUSD")

    closes = await get_price_data(asset)
    if not closes:
        await message.answer("❌ Не удалось получить данные.")
        return

    direction, accuracy = analyze_strategy(closes)
    last_price = closes[-1]

    if accuracy >= 65 and direction in ["Buy", "Sell"]:
        signal = generate_signal(direction, last_price)
        await message.answer(f"{signal}\n📊 Точность прогноза: <b>{accuracy}%</b>")
    elif accuracy < 60:
        await message.answer(f"⚠️ Риск велик, не время торговли (точность: {accuracy}%)")
    else:
        await message.answer("🤔 Недостаточно уверенности для сигнала.")


@dp.message(F.text.in_(["BTCUSD", "XAUUSD", "USTECH100"]))
async def set_asset(message: types.Message):
    user_id = message.from_user.id
    asset = message.text
    user_data[user_id]["asset"] = asset
    await message.answer(f"Актив установлен: {asset}")


@dp.message(F.text == "🔕 Mute")
async def mute_user(message: types.Message):
    user_id = message.from_user.id
    user_data[user_id]["mute"] = True
    await message.answer("🔕 Уведомления отключены")


@dp.message(F.text == "🔔 Unmute")
async def unmute_user(message: types.Message):
    user_id = message.from_user.id
    user_data[user_id]["mute"] = False
    await message.answer("🔔 Уведомления включены")


@dp.message(F.text == "📊 Статус")
async def show_status(message: types.Message):
    user_id = message.from_user.id
    data = user_data.get(user_id, {})
    await message.answer(f"""
<b>Ваши настройки:</b>
🔹 Актив: {data.get("asset", "BTCUSD")}
🔹 Mute: {"Да" if data.get("mute") else "Нет"}
🔹 Стратегия: {data.get("strategy", "default")}
🔹 Расписание: {data.get("schedule", "24/7")}
""")


# === MAIN ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
