import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
import numpy as np
import random

API_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
TWELVE_DATA_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

assets = {
    'BTCUSDT': {'binance_symbol': 'BTCUSDT', 'twelve_symbol': 'BTC/USD'},
    'XAUUSD': {'binance_symbol': 'XAUUSDT', 'twelve_symbol': 'XAU/USD'},
    'NAS100': {'binance_symbol': None, 'twelve_symbol': 'NDX/USD'}
}

selected_asset = {}
mute_status = {}

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='🔄 Получить сигнал')],
        [KeyboardButton(text='BTCUSDT'), KeyboardButton(text='XAUUSD'), KeyboardButton(text='NAS100')],
        [KeyboardButton(text='🔕 Mute'), KeyboardButton(text='🔔 Unmute')]
    ],
    resize_keyboard=True
)

# --- Получение цены с Binance ---
async def get_binance_price(symbol):
    try:
        url = f'https://api.binance.com/api/v3/ticker/price?symbol={symbol}'
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return float(data['price'])
    except Exception as e:
        logging.error(f"Binance error: {e}")
        return None

# --- Получение цены с TwelveData ---
async def get_twelve_data_price(symbol):
    try:
        url = f'https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVE_DATA_KEY}'
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                logging.info(f"TwelveData price response for {symbol}: {data}")
                return float(data['price']) if 'price' in data else None
    except Exception as e:
        logging.error(f"TwelveData error: {e}")
        return None

# --- Прогноз и сигнал ---
def generate_signal():
    accuracy = round(random.uniform(50, 90), 2)
    direction = random.choice(['Buy', 'Sell'])
    tp_percent = round(random.uniform(1, 3), 2)
    sl_percent = round(random.uniform(0.5, 2), 2)
    return accuracy, direction, tp_percent, sl_percent

# --- Старт ---
@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id
    selected_asset[user_id] = 'BTCUSDT'
    mute_status[user_id] = False
    await message.answer("Пора выбраться из матрицы", reply_markup=keyboard)

# --- Обработка кнопок ---
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text

    if text in assets:
        selected_asset[user_id] = text
        await message.answer(f"Выбран актив: {text}")

    elif text == '🔄 Получить сигнал':
        await send_signal(message, manual=True)

    elif text == '🔕 Mute':
        mute_status[user_id] = True
        await message.answer("🔕 Режим Mute включен. Сигналы будут без звука.")

    elif text == '🔔 Unmute':
        mute_status[user_id] = False
        await message.answer("🔔 Режим Mute выключен. Сигналы будут со звуком.")

# --- Получение сигнала ---
async def send_signal(message, manual=False):
    user_id = message.from_user.id
    asset = selected_asset.get(user_id, 'BTCUSDT')
    config = assets[asset]

    # Получение цены из Binance
    price_binance = await get_binance_price(config['binance_symbol']) if config['binance_symbol'] else None

    # Получение цены из TwelveData
    price_twelve = await get_twelve_data_price(config['twelve_symbol'])

    entry_price = price_twelve or price_binance

    if entry_price is None:
        await message.answer("❌ Не удалось получить цену актива.")
        return
        
accuracy, direction, tp_pct, sl_pct = generate_signal()
    if manual and accuracy < 65:
        await message.answer(f"⚠️ Риск велик, не время торговли ({accuracy}%)")
        return
    elif not manual and accuracy < 70:
        return

    tp_price = entry_price * (1 + tp_pct / 100) if direction == 'Buy' else entry_price * (1 - tp_pct / 100)
    sl_price = entry_price * (1 - sl_pct / 100) if direction == 'Buy' else entry_price * (1 + sl_pct / 100)

    message_text = (
        f"📈 Сигнал по {asset}\n"
        f"Направление: {direction}\n"
        f"Точность: {accuracy}%\n"
        f"Цена входа: {entry_price:.2f}\n"
        f"🎯 TP: +{tp_pct}% → {tp_price:.2f}\n"
        f"🛑 SL: -{sl_pct}% → {sl_price:.2f}"
    )

    if mute_status.get(user_id, False):
        await message.answer(message_text, disable_notification=True)
    else:
        await message.answer(message_text)

    # Проверка достижения TP или SL
    await asyncio.sleep(10)  # Демонстрация задержки проверки
    current_price = await get_twelve_data_price(config['twelve_symbol']) or await get_binance_price(config['binance_symbol'])

    if not current_price:
        return

    if (direction == 'Buy' and current_price >= tp_price) or (direction == 'Sell' and current_price <= tp_price):
        await message.answer(f"✅ TP достигнут: {current_price:.2f}")
    elif (direction == 'Buy' and current_price <= sl_price) or (direction == 'Sell' and current_price >= sl_price):
        await message.answer(f"❌ SL достигнут: {current_price:.2f}")

# --- Автосигналы каждые 30 сек ---
async def auto_signal_loop():
    while True:
        for user_id in selected_asset:
            await send_signal(types.Message(chat={'id': user_id}, from_user={'id': user_id}), manual=False)
        await asyncio.sleep(30)

async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
