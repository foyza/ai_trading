import asyncio
import datetime
import random
import yfinance as yf
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

API_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Пользовательские настройки
user_settings = {
    "asset": "BTC-USD",
    "schedule": {"start": "00:00", "end": "23:59"}
}

assets = {
    "BTCUSD": "BTC-USD",
    "XAUUSD": "GC=F",
    "USTECH100": "^NDX"
}

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="📈 Выбрать актив"), KeyboardButton(text="⏰ Настроить время")]
    ],
    resize_keyboard=True
)

asset_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD")],
        [KeyboardButton(text="USTECH100"), KeyboardButton(text="🔙 Назад")]
    ],
    resize_keyboard=True
)

time_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏰ Время: 09:00-17:00"), KeyboardButton(text="⏰ Время: 00:00-23:59")],
        [KeyboardButton(text="🔙 Назад")]
    ],
    resize_keyboard=True
)

def in_schedule():
    now = datetime.datetime.now().time()
    start = datetime.datetime.strptime(user_settings['schedule']['start'], "%H:%M").time()
    end = datetime.datetime.strptime(user_settings['schedule']['end'], "%H:%M").time()
    return start <= now <= end

def fetch_price(symbol):
    data = yf.download(tickers=symbol, period="1d", interval="1m")
    if data.empty:
        return None
    return round(data['Close'][-1], 2)

def predict_signal():
    accuracy = round(random.uniform(50, 100), 2)
    direction = random.choice(["Buy", "Sell"])
    tp_pct = round(random.uniform(1.0, 3.0), 2)
    sl_pct = round(random.uniform(0.5, 2.0), 2)
    return accuracy, direction, tp_pct, sl_pct

def format_signal(asset, accuracy, direction, entry, tp_pct, sl_pct):
    tp_price = round(entry * (1 + tp_pct/100 if direction == "Buy" else 1 - tp_pct/100), 2)
    sl_price = round(entry * (1 - sl_pct/100 if direction == "Buy" else 1 + sl_pct/100), 2)
    return (
        f"📡 <b>Сигнал по {asset}</b>\n"
        f"🎯 Направление: <b>{direction}</b>\n"
        f"🎯 Точность прогноза: <b>{accuracy}%</b>\n"
        f"💰 Цена входа: <b>{entry}</b>\n"
        f"✅ TP: <b>{tp_pct}%</b> → <b>{tp_price}</b>\n"
        f"❌ SL: <b>{sl_pct}%</b> → <b>{sl_price}</b>"
    )

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Пора выбраться из матрицы 🧠💥", reply_markup=keyboard)

@dp.message(lambda msg: msg.text == "📈 Выбрать актив")
async def choose_asset(message: Message):
    await message.answer("Выберите актив:", reply_markup=asset_keyboard)

@dp.message(lambda msg: msg.text == "⏰ Настроить время")
async def choose_time(message: Message):
    await message.answer("Выберите торговое время:", reply_markup=time_keyboard)

@dp.message(lambda msg: msg.text == "🔄 Получить сигнал")
async def manual_signal(message: Message):
    if not in_schedule():
        await message.answer("⏱ Сейчас не входит в торговое время.")
        return
    accuracy, direction, tp, sl = predict_signal()
    price = fetch_price(user_settings["asset"])
    if not price:
        await message.answer("❌ Не удалось получить цену.")
        return
    if accuracy >= 65:
        text = format_signal(user_settings["asset"], accuracy, direction, price, tp, sl)
        await message.answer(text, parse_mode=ParseMode.HTML)
    elif accuracy < 60:
        await message.answer(f"⚠️ Риск велик, не время торговли (Точность: {accuracy}%)")

@dp.message(lambda msg: msg.text in assets)
async def set_asset(message: Message):
    user_settings["asset"] = assets[message.text]
    await message.answer(f"✅ Актив установлен: {message.text}", reply_markup=keyboard)

@dp.message(lambda msg: msg.text.startswith("⏰ Время:"))
async def set_time(message: Message):
time_range = message.text.split(": ")[1]
    start, end = time_range.split("-")
    user_settings["schedule"] = {"start": start, "end": end}
    await message.answer(f"✅ Время установлено: {start}-{end}", reply_markup=keyboard)

@dp.message(lambda msg: msg.text == "🔙 Назад")
async def back_to_main(message: Message):
    await message.answer("🔙 Главное меню", reply_markup=keyboard)

async def auto_signal_loop():
    while True:
        if in_schedule():
            accuracy, direction, tp, sl = predict_signal()
            if accuracy > 70:
                price = fetch_price(user_settings["asset"])
                if price:
                    text = format_signal(user_settings["asset"], accuracy, direction, price, tp, sl)
                    await bot.send_message(chat_id=813631865, text=text, parse_mode=ParseMode.HTML)
        await asyncio.sleep(60)  # проверяем каждую минуту

async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
