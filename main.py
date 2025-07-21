import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.enums.parse_mode import ParseMode
from binance import AsyncClient
from datetime import datetime
from aiogram.filters import CommandStart

API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVE_DATA_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"

# Инициализация
bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()
client: AsyncClient = None

# Состояние по пользователям
user_assets = {}
user_mute = {}
user_strategy = {}
user_schedule = {}

# Клавиатура
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
        [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
        [KeyboardButton(text="🎯 Стратегия"), KeyboardButton(text="📊 Статус")],
    ],
    resize_keyboard=True
)

# Binance API
async def get_binance_price(symbol: str) -> float:
    try:
        ticker = await client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        print(f"Binance error: {e}")
        return None

# TwelveData API
async def get_twelvedata_price(symbol: str) -> float:
    url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVE_DATA_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            return float(data["price"])

# Финальная функция получения цены
async def get_price(asset: str) -> float:
    if asset == "USTECH100":
        return await get_twelvedata_price("NAS100")
    elif asset in ["BTCUSD", "XAUUSD"]:
        binance_symbol = "BTCUSDT" if asset == "BTCUSD" else "XAUUSDT"
        twelvedata_symbol = "BTC/USD" if asset == "BTCUSD" else "XAU/USD"
        binance_price = await get_binance_price(binance_symbol)
        twelve_price = await get_twelvedata_price(twelvedata_symbol)
        return round((binance_price + twelve_price) / 2, 2)
    else:
        return 0.0

# Приветствие
@router.message(CommandStart())
async def start_handler(message: types.Message):
    user_assets[message.from_user.id] = "BTCUSD"
    user_mute[message.from_user.id] = False
    user_strategy[message.from_user.id] = "MA + RSI + MACD"
    user_schedule[message.from_user.id] = {
        "BTCUSD": {"days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "hours": [0, 24]},
        "XAUUSD": {"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "hours": [0, 24]},
        "USTECH100": {"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "hours": [0, 24]},
    }
    await message.answer("Пора выбраться из матрицы", reply_markup=keyboard)

# Обработка кнопок
@router.message(F.text.in_({"BTCUSD", "XAUUSD", "USTECH100"}))
async def asset_handler(message: types.Message):
    user_assets[message.from_user.id] = message.text
    await message.answer(f"Актив установлен: {message.text}")

@router.message(F.text == "🔕 Mute")
async def mute(message: types.Message):
    user_mute[message.from_user.id] = True
    await message.answer("🔕 Уведомления отключены")

@router.message(F.text == "🔔 Unmute")
async def unmute(message: types.Message):
    user_mute[message.from_user.id] = False
    await message.answer("🔔 Уведомления включены")

@router.message(F.text == "📊 Статус")
async def status(message: types.Message):
    asset = user_assets.get(message.from_user.id, "BTCUSD")
    schedule = user_schedule.get(message.from_user.id, {}).get(asset)
    days = ", ".join(schedule["days"])
    hours = f"{schedule['hours'][0]}:00 - {schedule['hours'][1]}:00"
    await message.answer(f"<b>Текущий актив:</b> {asset}\n<b>Рабочие дни:</b> {days}\n<b>Часы:</b> {hours}")

# Получение сигнала
@router.message(F.text == "🔄 Получить сигнал")
async def get_signal(message: types.Message):
    asset = user_assets.get(message.from_user.id, "BTCUSD")
    price = await get_price(asset)
    if price:
        await message.answer(f"<b>{asset}</b>\nТекущая цена: {price}")
    else:
        await message.answer("❌ Не удалось получить цену")

# Запуск
async def main():
    global client
    client = await AsyncClient.create()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
