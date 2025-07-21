import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums.parse_mode import ParseMode
import aiohttp
import logging
import numpy as np
import pandas as pd
from dotenv import load_dotenv
import os

# Загрузка токенов
load_dotenv()
API_TOKEN = os.getenv('8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA')
TWELVEDATA_API_KEY = os.getenv('5e5e950fa71c416e9ffdb86fce72dc4f')

ASSETS = {
    'BTCUSD': 'BTC/USD',
    'XAUUSD': 'XAU/USD',
    'USTECH100': 'NAS100'
}

user_settings = {}  # user_id: {'asset': 'BTCUSD', 'mute': False, 'strategy': 'MA+RSI+MACD'}

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Кнопки
main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔄 Получить сигнал")],
    [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
    [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
    [KeyboardButton(text="🎯 Стратегия"), KeyboardButton(text="🕒 Расписание")],
    [KeyboardButton(text="📊 Статус")]
], resize_keyboard=True)

# Команды
@dp.message(F.text == "/start")
async def start_handler(msg: types.Message):
    user_settings[msg.from_user.id] = {
        'asset': 'BTCUSD',
        'mute': False,
        'strategy': 'MA+RSI+MACD'
    }
    await msg.answer("Пора выбраться из матрицы", reply_markup=main_kb)

@dp.message(F.text.in_(['BTCUSD', 'XAUUSD', 'USTECH100']))
async def asset_select(msg: types.Message):
    user_settings[msg.from_user.id]['asset'] = msg.text
    await msg.answer(f"✅ Актив установлен: <b>{msg.text}</b>")

@dp.message(F.text == "🔕 Mute")
async def mute_on(msg: types.Message):
    user_settings[msg.from_user.id]['mute'] = True
    await msg.answer("🔕 Уведомления отключены")

@dp.message(F.text == "🔔 Unmute")
async def mute_off(msg: types.Message):
    user_settings[msg.from_user.id]['mute'] = False
    await msg.answer("🔔 Уведомления включены")

@dp.message(F.text == "🎯 Стратегия")
async def strategy_select(msg: types.Message):
    current = user_settings[msg.from_user.id]['strategy']
    new = "Bollinger+Volume" if current == "MA+RSI+MACD" else "MA+RSI+MACD"
    user_settings[msg.from_user.id]['strategy'] = new
    await msg.answer(f"🎯 Стратегия установлена: <b>{new}</b>")

@dp.message(F.text == "📊 Статус")
async def status(msg: types.Message):
    u = user_settings[msg.from_user.id]
    await msg.answer(f"""📊 <b>Ваши настройки:</b>
Актив: {u['asset']}
Стратегия: {u['strategy']}
Mute: {"Вкл" if u['mute'] else "Выкл"}""")

@dp.message(F.text == "🕒 Расписание")
async def schedule(msg: types.Message):
    await msg.answer("🕒 Расписание пока не настраивается. По умолчанию — круглосуточно.")

@dp.message(F.text == "🔄 Получить сигнал")
async def manual_signal(msg: types.Message):
    uid = msg.from_user.id
    asset = user_settings[uid]['asset']
    strategy = user_settings[uid]['strategy']
    signal = await generate_signal(asset, strategy)
    if signal['accuracy'] >= 65:
        await msg.answer(format_signal(signal), disable_notification=user_settings[uid]['mute'])
    elif signal['accuracy'] < 60:
        await msg.answer(f"⚠️ Риск велик, не время торговли (точность: {signal['accuracy']}%)")

# Сигналы
async def generate_signal(symbol: str, strategy: str):
    prices = await get_prices(symbol)
    if not prices or len(prices) < 50:
        return {'accuracy': 0}

    if strategy == "MA+RSI+MACD":
        ma10 = np.mean(prices[-10:])
        ma50 = np.mean(prices[-50:])
        rsi = calculate_rsi(prices)
        macd, signal_macd = calculate_macd(prices)

        buy_count = 0
        sell_count = 0

        if ma10 > ma50:
            buy_count += 1
        else:
            sell_count += 1

        if rsi < 30:
            buy_count += 1
        elif rsi > 70:
            sell_count += 1

        if macd > signal_macd:
            buy_count += 1
        else:
            sell_count += 1

        agree = buy_count == 3 or sell_count == 3
        accuracy = 75 if agree else 50 if buy_count + sell_count == 2 else 40

        if not agree:
            return {'accuracy': accuracy}

        direction = "Buy" if buy_count == 3 else "Sell"

    else:  # Bollinger+Volume
        df = pd.Series(prices)
        ma = df.rolling(window=20).mean()
        std = df.rolling(window=20).std()
        upper = ma + 2 * std
        lower = ma - 2 * std
        price = df.iloc[-1]

        if price > upper.iloc[-1]:
            direction = "Sell"
        elif price < lower.iloc[-1]:
            direction = "Buy"
        else:
            return {'accuracy': 50}

        accuracy = 70

    entry_price = round(prices[-1], 2)
    tp = round(entry_price * (1.02 if direction == "Buy" else 0.98), 2)
    sl = round(entry_price * (0.985 if direction == "Buy" else 1.015), 2)

    return {
        'asset': symbol,
        'direction': direction,
        'entry': entry_price,
        'tp_price': tp,
        'sl_price': sl,
        'tp_percent': 2,
        'sl_percent': 1.5,
        'accuracy': accuracy
    }

def format_signal(s):
    return f"""📈 <b>Сигнал по {s['asset']}</b>
📊 Направление: <b>{s['direction']}</b>
💰 Вход: <code>{s['entry']}</code>
🎯 TP: +{s['tp_percent']}% → <code>{s['tp_price']}</code>
🛑 SL: -{s['sl_percent']}% → <code>{s['sl_price']}</code>
✅ Точность прогноза: <b>{s['accuracy']}%</b>"""

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down else 0.01
    return 100 - (100 / (1 + rs))

def calculate_macd(prices):
    df = pd.Series(prices)
    ema12 = df.ewm(span=12, adjust=False).mean()
    ema26 = df.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd.iloc[-1], signal.iloc[-1]

async def get_prices(asset: str):
    interval = "1min"
    url = f"https://api.twelvedata.com/time_series?symbol={ASSETS[asset]}&interval={interval}&apikey={TWELVEDATA_API_KEY}&outputsize=50"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                js = await resp.json()
                if 'values' not in js:
                    return []
                closes = [float(x['close']) for x in reversed(js['values'])]
                return closes
    except Exception as e:
        print("Ошибка получения данных:", e)
        return []

# Авторассылка
async def auto_signal_sender():
    while True:
        await asyncio.sleep(60)
        for uid in user_settings:
            asset = user_settings[uid]['asset']
            strategy = user_settings[uid]['strategy']
            mute = user_settings[uid]['mute']
            signal = await generate_signal(asset, strategy)
            if signal['accuracy'] >= 70:
                try:
                    await bot.send_message(uid, format_signal(signal), disable_notification=mute)
                except:
                    continue

# Запуск
async def main():
    asyncio.create_task(auto_signal_sender())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
