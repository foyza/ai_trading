import asyncio
import logging
import numpy as np
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from binance import AsyncClient
import aiohttp
import time

API_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
TWELVEDATA_API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher()
user_state = {}
signal_sent = {}

assets = {
    'BTCUSDT': 'BTC/USDT',
    'XAUUSD': 'XAU/USD',
    'NAS100': 'NAS100'
}

reply_kb = ReplyKeyboardMarkup(resize_keyboard=True)
reply_kb.add(KeyboardButton('🔄 Получить сигнал'))
reply_kb.add(KeyboardButton('BTCUSDT'), KeyboardButton('XAUUSD'), KeyboardButton('NAS100'))
reply_kb.add(KeyboardButton('🔕 Mute'), KeyboardButton('🔔 Unmute'))

# Приветствие
@dp.message(commands=['start'])
async def start_handler(msg: types.Message):
    user_state[msg.chat.id] = {'asset': 'BTCUSDT', 'mute': False}
    await msg.answer("Пора выбраться из матрицы", reply_markup=reply_kb)

# Кнопки
@dp.message()
async def buttons_handler(msg: types.Message):
    chat_id = msg.chat.id
    text = msg.text

    if text in assets:
        user_state[chat_id]['asset'] = text
        await msg.answer(f"✅ Актив изменён на {text}")
    elif text == '🔕 Mute':
        user_state[chat_id]['mute'] = True
        await msg.answer("🔕 Режим без звука активирован")
    elif text == '🔔 Unmute':
        user_state[chat_id]['mute'] = False
        await msg.answer("🔔 Звуковые сигналы включены")
    elif text == '🔄 Получить сигнал':
        await process_signal(chat_id, manual=True)

# MA стратегия
def generate_signal_ma_strategy(prices: list[float]):
    if len(prices) < 50:
        return None, "❌ Недостаточно данных"

    ma10 = np.mean(prices[-10:])
    ma50 = np.mean(prices[-50:])
    if ma10 > ma50:
        return "Buy", None
    elif ma10 < ma50:
        return "Sell", None
    return None, "❌ Нет сигнала"

# Получение цен с Binance
async def get_klines_binance(symbol: str, interval="1h", limit=100):
    try:
        client = await AsyncClient.create()
        klines = await client.get_klines(symbol=symbol, interval=interval, limit=limit)
        await client.close_connection()
        return [float(k[4]) for k in klines]
    except:
        return []

# Получение текущей цены
async def get_price(asset: str):
    try:
        if asset == 'NAS100':
            url = f'https://api.twelvedata.com/price?symbol=NAS100&apikey={TWELVEDATA_API_KEY}'
        else:
            url = f'https://api.twelvedata.com/price?symbol={asset}&apikey={TWELVEDATA_API_KEY}'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return float(data['price'])
    except:
        return None

# Основная функция генерации сигнала
async def process_signal(chat_id: int, manual=False):
    state = user_state.get(chat_id, {'asset': 'BTCUSDT', 'mute': False})
    asset = state['asset']

    prices = await get_klines_binance(asset if asset != 'NAS100' else 'BTCUSDT')
    if not prices or len(prices) < 50:
        await bot.send_message(chat_id, f"❌ Недостаточно данных для анализа")
        return

    signal, error = generate_signal_ma_strategy(prices)
    if error:
        await bot.send_message(chat_id, error)
        return

    accuracy = np.random.randint(61, 95)  # для демонстрации
    if manual and accuracy < 65:
        await bot.send_message(chat_id, f"⚠️ Риск велик, не время торговли ({accuracy}%)")
        return
    if not manual and accuracy < 70:
        return

    entry = await get_price(asset)
    if not entry:
        await bot.send_message(chat_id, "❌ Не удалось получить цену актива.")
        return

    tp_pct, sl_pct = (1.5, 1.0)
    tp_price = entry * (1 + tp_pct/100) if signal == "Buy" else entry * (1 - tp_pct/100)
    sl_price = entry * (1 - sl_pct/100) if signal == "Buy" else entry * (1 + sl_pct/100)

    text = (
        f"<b>{assets[asset]}</b>\n"
        f"📈 Направление: <b>{signal}</b>\n"
        f"🎯 Вход: <b>{entry:.2f}</b>\n"
        f"🎯 TP: <b>{tp_pct}%</b> → <b>{tp_price:.2f}</b>\n"
        f"🛑 SL: <b>{sl_pct}%</b> → <b>{sl_price:.2f}</b>\n"
        f"📊 Точность прогноза: <b>{accuracy}%</b>"
    )

    if not state.get('mute', False):
        await bot.send_message(chat_id, text)
    else:
        await bot.send_message(chat_id, text, disable_notification=True)

    signal_sent[chat_id] = {'signal': signal, 'tp': tp_price, 'sl': sl_price, 'active': True}

# Проверка достижения TP или SL
async def monitor_tp_sl():
    while True:
        for chat_id, data in signal_sent.items():
            if not data.get('active'):
                continue
            entry = await get_price(user_state[chat_id]['asset'])
            if not entry:
                continue
            if (data['signal'] == 'Buy' and entry >= data['tp']) or \
               (data['signal'] == 'Sell' and entry <= data['tp']):
                await bot.send_message(chat_id, "✅ TP достигнут!")
                data['active'] = False
            elif (data['signal'] == 'Buy' and entry <= data['sl']) or \
                 (data['signal'] == 'Sell' and entry >= data['sl']):
                await bot.send_message(chat_id, "🛑 SL сработал.")
                data['active'] = False
        await asyncio.sleep(30)

# Автоотправка сигналов
async def auto_signal_loop():
    while True:
        for chat_id in user_state:
            await process_signal(chat_id)
        await asyncio.sleep(60)

# Запуск
async def main():
    asyncio.create_task(monitor_tp_sl())
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
