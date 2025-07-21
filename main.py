import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
import random
import aiohttp
from binance import AsyncClient

API_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
TWELVE_DATA_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'

bot = Bot(token=API_TOKEN, parse_mode='HTML')
dp = Dispatcher()
active_asset = 'BTCUSDT'
mute_mode = False

assets = {
    'BTCUSDT': {'binance_symbol': 'BTCUSDT', 'twelve_symbol': 'BTC/USD'},
    'XAUUSD': {'binance_symbol': 'XAUUSDT', 'twelve_symbol': 'XAU/USD'},
    'NAS100': {'binance_symbol': None, 'twelve_symbol': 'NAS100'}
}

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='🔄 Получить сигнал')],
        [KeyboardButton(text='BTCUSDT'), KeyboardButton(text='XAUUSD'), KeyboardButton(text='NAS100')],
        [KeyboardButton(text='🔇 Mute'), KeyboardButton(text='🔊 Unmute')]
    ],
    resize_keyboard=True
)

def simulate_model_prediction():
    direction = random.choice(['Buy', 'Sell'])
    confidence = round(random.uniform(55, 85), 2)
    tp_pct = round(random.uniform(1.2, 3), 2)
    sl_pct = round(random.uniform(0.8, 2), 2)
    return direction, confidence, tp_pct, sl_pct

async def get_binance_price(symbol):
    try:
        client = await AsyncClient.create()
        ticker = await client.get_symbol_ticker(symbol=symbol)
        await client.close_connection()
        return float(ticker['price'])
    except Exception as e:
        logging.error(f"Binance price error: {e}")
        return None

async def get_twelve_data_price(symbol):
    try:
        url = f'https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVE_DATA_KEY}'
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return float(data['price']) if 'price' in data else None
    except Exception as e:
        logging.error(f"TwelveData error: {e}")
        return None

async def get_current_price(symbol_key):
    asset_info = assets[symbol_key]
    binance_price = await get_binance_price(asset_info['binance_symbol']) if asset_info['binance_symbol'] else None
    twelve_price = await get_twelve_data_price(asset_info['twelve_symbol'])
    prices = [p for p in [binance_price, twelve_price] if p]
    return round(sum(prices) / len(prices), 2) if prices else None

def build_signal_message(direction, price, tp_pct, sl_pct, confidence):
    tp_price = round(price * (1 + tp_pct / 100), 2) if direction == 'Buy' else round(price * (1 - tp_pct / 100), 2)
    sl_price = round(price * (1 - sl_pct / 100), 2) if direction == 'Buy' else round(price * (1 + sl_pct / 100), 2)
    return (
        f"<b>📊 Новый сигнал по {active_asset}</b>\n"
        f"📈 Направление: <b>{direction}</b>\n"
        f"🎯 Точность: <b>{confidence}%</b>\n"
        f"💰 Цена входа: <b>{price}</b>\n"
        f"✅ TP: <b>{tp_pct}%</b> → <b>{tp_price}</b>\n"
        f"❌ SL: <b>{sl_pct}%</b> → <b>{sl_price}</b>"
    )

async def send_signal(chat_id):
    direction, confidence, tp_pct, sl_pct = simulate_model_prediction()
    price = await get_current_price(active_asset)

    if not price:
        await bot.send_message(chat_id, "❌ Не удалось получить цену актива.")
        return

    if confidence < 60:
        await bot.send_message(chat_id, f"⚠️ Риск велик, не время торговли ({confidence}%)")
        return

    if confidence >= 65:
        message = build_signal_message(direction, price, tp_pct, sl_pct, confidence)
        await bot.send_message(chat_id, message, disable_notification=mute_mode)

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("Пора выбраться из матрицы", reply_markup=keyboard)

@dp.message()
async def handle_message(message: types.Message):
    global active_asset, mute_mode

    if message.text == '🔄 Получить сигнал':
        await send_signal(message.chat.id)
    elif message.text in assets:
        active_asset = message.text
        await message.answer(f"✅ Актив установлен: <b>{active_asset}</b>")
    elif message.text == '🔇 Mute':
        mute_mode = True
        await message.answer("🔕 Режим Mute включён.")
    elif message.text == '🔊 Unmute':
        mute_mode = False
        await message.answer("🔔 Звуковые уведомления включены.")

async def auto_signal_loop():
    while True:
        direction, confidence, tp_pct, sl_pct = simulate_model_prediction()
        price = await get_current_price(active_asset)
        if confidence >= 70 and price:
            message = build_signal_message(direction, price, tp_pct, sl_pct, confidence)
            await bot.send_message(chat_id='813631865', text=message, disable_notification=mute_mode)
        await asyncio.sleep(20)

async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
        
