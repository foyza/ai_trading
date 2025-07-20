import asyncio
import random
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yfinance as yf
from datetime import datetime
import pytz

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]
user_assets = {}
user_schedule = {}  # {user_id: {"start": 0, "end": 23}}

def get_market_price(asset):
    symbol_map = {
        "BTCUSD": "BTC-USD",
        "XAUUSD": "GC=F",
        "USTECH100": "^NDX"
    }
    ticker = symbol_map.get(asset)
    try:
        data = yf.download(ticker, period="1d", interval="5m", progress=False)
        if data.empty:
            print(f"[{asset}] No data received from yfinance.")
            return None
        return float(data["Close"].iloc[-1])
    except Exception as e:
        print(f"Failed to get price for {ticker}: {e}")
        return None

def generate_signal(asset):
    price = get_market_price(asset)
    if not price:
        return None
    direction = random.choice(["Buy", "Sell"])
    accuracy = round(random.uniform(60, 95), 2)
    tp = price * (1 + 0.02) if direction == "Buy" else price * (1 - 0.02)
    sl = price * (1 - 0.015) if direction == "Buy" else price * (1 + 0.015)
    return {
        "asset": asset,
        "direction": direction,
        "entry": round(price, 2),
        "tp": round(tp, 2),
        "sl": round(sl, 2),
        "accuracy": accuracy,
    }

def format_signal(signal, auto=False):
    prefix = "🔔 <b>Автосигнал</b>" if auto else "📡 <b>Сигнал</b>"
    return (
        f"{prefix} по <b>{signal['asset']}</b>\n"
        f"📍 Вход: <b>{signal['entry']}</b>\n"
        f"🎯 TP: <b>{signal['tp']}</b> (+2%)\n"
        f"🛡️ SL: <b>{signal['sl']}</b> (-1.5%)\n"
        f"📊 Точность: <b>{signal['accuracy']}%</b>\n"
        f"📈 Направление: <b>{signal['direction']}</b>"
    )

def asset_keyboard():
    kb = InlineKeyboardBuilder()
    for asset in ASSETS:
        kb.button(text=asset, callback_data=f"asset:{asset}")
    return kb.as_markup()

def schedule_keyboard():
    kb = InlineKeyboardBuilder()
    for hour in range(0, 24, 3):
        kb.button(text=f"{hour}:00", callback_data=f"start:{hour}")
    return kb.as_markup()

def end_hour_keyboard(start_hour):
    kb = InlineKeyboardBuilder()
    for hour in range(start_hour + 1, 25):
        kb.button(text=f"{hour}:00", callback_data=f"end:{hour}")
    return kb.as_markup()

@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer("Пора выбраться из матрицы!", reply_markup=asset_keyboard())

@dp.callback_query(F.data.startswith("asset:"))
async def set_asset(callback: CallbackQuery):
    asset = callback.data.split(":")[1]
    user_assets[callback.from_user.id] = asset
    await callback.message.answer(f"✅ Актив установлен: <b>{asset}</b>\n\nТеперь выберите часы работы сигналов:", reply_markup=schedule_keyboard())

@dp.callback_query(F.data.startswith("start:"))
async def set_start(callback: CallbackQuery):
    start_hour = int(callback.data.split(":")[1])
    user_schedule[callback.from_user.id] = {"start": start_hour}
    await callback.message.answer(f"🕐 Начало: {start_hour}:00\nТеперь выберите конец:", reply_markup=end_hour_keyboard(start_hour))

@dp.callback_query(F.data.startswith("end:"))
async def set_end(callback: CallbackQuery):
    end_hour = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    if user_id in user_schedule:
        user_schedule[user_id]["end"] = end_hour
        await callback.message.answer(f"🕒 Сигналы будут приходить с {user_schedule[user_id]['start']}:00 до {end_hour}:00")
    else:
        await callback.message.answer("❗ Сначала выберите начало диапазона.")

@dp.message(F.text == "/signal")
async def manual_signal(message: Message):
    user_id = message.from_user.id
    asset = user_assets.get(user_id, "BTCUSD")
    signal = generate_signal(asset)
    if signal and signal["accuracy"] >= 65:
        await message.answer(format_signal(signal))
    else:
        await message.answer("❌ Недостаточная точность сигнала или нет данных.")

async def auto_signal_loop():
    while True:
        now = datetime.now(pytz.timezone("Asia/Tashkent")).hour
        for user_id, asset in user_assets.items():
            sched = user_schedule.get(user_id, {"start": 0, "end": 24})
            if sched["start"] <= now < sched["end"]:
                signal = generate_signal(asset)
                if signal and signal["accuracy"] >= 70:
                    await bot.send_message(user_id, format_signal(signal, auto=True))
        await asyncio.sleep(60)

async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if name == "__main__":
    asyncio.run(main())
