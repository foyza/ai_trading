import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from datetime import datetime

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
bot = Bot(token=TOKEN)
dp = Dispatcher()

TRADABLE_ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]
user_trading_hours = {}

# Приветствие и кнопки
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📈 Запросить сигнал")],
        [KeyboardButton(text="📊 Выбрать актив")]
    ], resize_keyboard=True)
    await msg.answer("Пора выбереться из матрицы! Выбери действие ниже:", reply_markup=kb)

# Выбор актива
@dp.message(lambda msg: msg.text == "📊 Выбрать актив")
async def choose_asset(msg: Message):
    buttons = [[KeyboardButton(text=asset)] for asset in TRADABLE_ASSETS]
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await msg.answer("Выбери актив:", reply_markup=kb)

# Обработка сигнала
@dp.message(lambda msg: msg.text in TRADABLE_ASSETS or msg.text == "📈 Запросить сигнал")
async def send_signal(msg: Message):
    user_id = msg.from_user.id
    asset = msg.text if msg.text in TRADABLE_ASSETS else "BTCUSD"

    # Проверка времени
    now = datetime.utcnow().hour
    if user_id in user_trading_hours:
        hours = user_trading_hours[user_id].get(asset, {}).get("hours")
        if hours:
            start, end = hours
            if not (start <= now <= end):
                await msg.answer(f"⏰ Сейчас не торговое время для {asset}.")
                return

    # Заглушка сигнала
    signal = f"🔔 Сигнал по {asset}:\n📈 Take Profit: +2%\n📉 Stop Loss: -1.5%"
    await msg.answer(signal)

# Команда установки часов
@dp.message(Command("sethours"))
async def set_hours_cmd(msg: Message):
    parts = msg.text.split()
    if len(parts) != 4:
        await msg.answer("Формат: /sethours ASSET START END")
        return
    asset, start, end = parts[1], int(parts[2]), int(parts[3])
    if asset not in TRADABLE_ASSETS:
        await msg.answer("⛔️ Недопустимый актив.")
        return

    user_id = msg.from_user.id
    user_trading_hours.setdefault(user_id, {})
    user_trading_hours[user_id].setdefault(asset, {})
    user_trading_hours[user_id][asset]["hours"] = (start, end)

    await msg.answer(f"✅ Часы торговли для {asset} установлены: {start}:00 - {end}:00")

# Запуск бота
async def main():
    print("✅ Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
