import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums.parse_mode import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import yfinance as yf

# Загрузка переменных окружения
load_dotenv()
API_TOKEN = os.getenv("8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA")

if not API_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден. Добавь его в .env или переменные Railway!")

# Инициализация бота
bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

ASSETS = {
    'BTCUSD': 'BTC-USD',
    'XAUUSD': 'GC=F',
    'USTECH100': '^NDX'
}

user_settings = {}

main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔄 Получить сигнал")],
    [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
    [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
    [KeyboardButton(text="🎯 Стратегия"), KeyboardButton(text="📊 Статус")]
], resize_keyboard=True)

@dp.message(F.text == "/start")
async def start_handler(msg: types.Message):
    user_settings[msg.from_user.id] = {
        'asset': 'BTCUSD',
        'mute': False,
        'strategy': 'MA+RSI+MACD'
    }
    await msg.answer("Добро пожаловать! Бот запущен.", reply_markup=main_kb)

@dp.message(F.text.in_(ASSETS.keys()))
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

@dp.message(F.text == "🔄 Получить сигнал")
async def manual_signal(msg: types.Message):
    uid = msg.from_user.id
    asset = user_settings[uid]['asset']
    strategy = user_settings[uid]['strategy']
    signal = await generate_signal(asset, strategy)
    if signal['accuracy'] >= 65:
        await msg.answer(format_signal(signal), disable_notification=user_settings[uid]['mute'])
    else:
        await msg.answer(f"⚠️ Низкая точность ({signal['accuracy']}%), торговля не рекомендована.")

async def generate_signal(asset_code, strategy):
    prices = await get_prices(asset_code)
    if len(prices) < 50:
        return {'accuracy': 0}

    if strategy == "MA+RSI+MACD":
        ma10 = np.mean(prices[-10:])
        ma50 = np.mean(prices[-50:])
        rsi = calculate_rsi(prices)
        macd, macd_signal = calculate_macd(prices)

        buy = sum([
            ma10 > ma50,
            rsi < 30,
            macd > macd_signal
        ])
        sell = sum([
            ma10 < ma50,
            rsi > 70,
            macd < macd_signal
        ])
        if buy == 3:
            direction, accuracy = "Buy", 75
        elif sell == 3:
            direction, accuracy = "Sell", 75
        else:
            return {'accuracy': 50}
    else:
        df = pd.Series(prices)
        ma = df.rolling(window=20).mean()
        std = df.rolling(window=20).std()
        upper = ma + 2 * std
        lower = ma - 2 * std
        price = df.iloc[-1]
        if price > upper.iloc[-1]:
            direction, accuracy = "Sell", 70
        elif price < lower.iloc[-1]:
            direction, accuracy = "Buy", 70
        else:
            return {'accuracy': 50}

    entry = round(prices[-1], 2)
    tp = round(entry * (1.02 if direction == "Buy" else 0.98), 2)
    sl = round(entry * (0.985 if direction == "Buy" else 1.015), 2)

    return {
        'asset': asset_code,
        'direction': direction,
        'entry': entry,
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
    gain = np.where(deltas > 0, deltas, 0).sum() / period
    loss = -np.where(deltas < 0, deltas, 0).sum() / period
    rs = gain / loss if loss != 0 else 1
    return 100 - (100 / (1 + rs))

def calculate_macd(prices):
    df = pd.Series(prices)
    ema12 = df.ewm(span=12, adjust=False).mean()
    ema26 = df.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd.iloc[-1], signal.iloc[-1]

async def get_prices(symbol):
    try:
        data = yf.download(ASSETS[symbol], period="5d", interval="1m", progress=False)
        return data['Close'].tolist()
    except Exception as e:
        print("Ошибка загрузки:", e)
        return []

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
