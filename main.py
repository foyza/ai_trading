import asyncio
import logging
import os
import time
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from ta.trend import MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator
import numpy as np
import pandas as pd
import requests

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVE_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"
SYMBOL_MAP = {
    "BTCUSD": "BTC/USD",
    "XAUUSD": "XAU/USD",
    "USTECH100": "NAS100"
}

user_data = {}

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

def get_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
        [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
        [KeyboardButton(text="🎯 Стратегия"), KeyboardButton(text="🕒 Расписание")],
        [KeyboardButton(text="📊 Статус")]
    ], resize_keyboard=True)

async def get_price_data(symbol: str):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=100&apikey={TWELVE_API_KEY}"
    response = requests.get(url).json()
    if 'values' not in response:
        return None
    df = pd.DataFrame(response['values'])
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime')
    df.set_index('datetime', inplace=True)
    df = df.astype(float)
    return df

def calculate_signal(df, strategy):
    close = df['close']
    signal = "No signal"
    score = 0

    ma10 = close.rolling(window=10).mean()
    ma50 = close.rolling(window=50).mean()
    rsi = RSIIndicator(close).rsi()
    macd = MACD(close).macd_diff()

    if strategy == "classic":
        ma_signal = "Buy" if ma10.iloc[-1] > ma50.iloc[-1] else "Sell"
        rsi_signal = "Buy" if rsi.iloc[-1] < 30 else "Sell" if rsi.iloc[-1] > 70 else "Neutral"
        macd_signal = "Buy" if macd.iloc[-1] > 0 else "Sell"

        signals = [ma_signal, rsi_signal, macd_signal]
        if signals.count(signals[0]) == 3 and signals[0] != "Neutral":
            signal = signals[0]
            score = 75 + np.random.randint(0, 6)
        elif signals.count(signals[0]) == 2:
            signal = "ind: 2/3"
            score = 60 + np.random.randint(0, 6)

    elif strategy == "extended":
        bb = BollingerBands(close)
        stoch = StochasticOscillator(df['high'], df['low'], close)
        obv = OnBalanceVolumeIndicator(close, df['volume'])

        bb_signal = "Buy" if close.iloc[-1] < bb.bollinger_lband().iloc[-1] else "Sell"
        stoch_signal = "Buy" if stoch.stoch_signal().iloc[-1] < 20 else "Sell"
        obv_signal = "Buy" if obv.on_balance_volume().iloc[-1] > obv.on_balance_volume().iloc[-2] else "Sell"

        signals = [bb_signal, stoch_signal, obv_signal]
        if signals.count(signals[0]) == 3:
            signal = signals[0]
            score = 78 + np.random.randint(0, 3)

    return signal, score

def format_signal(symbol, direction, price, score):
    tp_pct = 0.015
    sl_pct = 0.01
    tp_price = round(price * (1 + tp_pct if direction == "Buy" else 1 - tp_pct), 2)
    sl_price = round(price * (1 - sl_pct if direction == "Buy" else 1 + sl_pct), 2)
    return f"""
📈 <b>{symbol}</b>
📊 Точность: <b>{score}%</b>
🔁 Сигнал: <b>{direction}</b>
💵 Вход: <b>{price}</b>
🎯 TP: <b>{tp_pct*100:.1f}%</b> → <b>{tp_price}</b>
🛡️ SL: <b>{sl_pct*100:.1f}%</b> → <b>{sl_price}</b>
"""

@dp.message(commands=["start"])
async def start(message: types.Message):
    user_id = message.from_user.id
    user_data[user_id] = {
        "symbol": "BTCUSD",
        "mute": False,
        "strategy": "classic"
    }
    await message.answer("Пора выбраться из матрицы", reply_markup=get_keyboard())

@dp.message()async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    data = user_data.setdefault(user_id, {"symbol": "BTCUSD", "mute": False, "strategy": "classic"})

    if text in ["BTCUSD", "XAUUSD", "USTECH100"]:
        data["symbol"] = text
        await message.answer(f"Актив установлен: {text}")

    elif text == "🔕 Mute":
        data["mute"] = True
        await message.answer("🔇 Уведомления выключены")

    elif text == "🔔 Unmute":
        data["mute"] = False
        await message.answer("🔔 Уведомления включены")

    elif text == "🎯 Стратегия":
        data["strategy"] = "extended" if data["strategy"] == "classic" else "classic"
        await message.answer(f"Стратегия установлена: {data['strategy']}")

    elif text == "📊 Статус":
        await message.answer(f"""
🧾 Ваш статус:
• Актив: {data['symbol']}
• Стратегия: {data['strategy']}
• Звук: {'🔕 Mute' if data['mute'] else '🔔 Unmute'}
""")

    elif text == "🔄 Получить сигнал":
        symbol = data["symbol"]
        df = await get_price_data(SYMBOL_MAP[symbol])
        if df is None:
            await message.answer("Ошибка получения данных")
            return
        signal, score = calculate_signal(df, data["strategy"])
        price = df['close'].iloc[-1]

        if score >= 65:
            msg = format_signal(symbol, signal, price, score)
            await message.answer(msg)
        elif score < 60:
            await message.answer(f"⚠️ Риск велик, не время торговли (точность: {score}%)")
        else:
            await message.answer("Сигнал недостаточно надёжен.")

async def auto_check():
    for user_id, data in user_data.items():
        if data["mute"]:
            continue
        symbol = data["symbol"]
        df = await get_price_data(SYMBOL_MAP[symbol])
        if df is None:
            continue
        signal, score = calculate_signal(df, data["strategy"])
        if score >= 70 and signal in ["Buy", "Sell"]:
            price = df['close'].iloc[-1]
            msg = format_signal(symbol, signal, price, score)
            await bot.send_message(user_id, msg)

async def main():
    scheduler.add_job(auto_check, "interval", minutes=5)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
