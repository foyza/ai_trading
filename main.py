# main.py
import asyncio
import logging
import datetime as dt
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from binance.client import Client
import requests
import numpy as np
import pandas as pd

API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVEDATA_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
user_data = {}
mute_status = {}

ASSETS = {
    "BTCUSD": ("BTCUSDT", "BTC/USD"),
    "XAUUSD": ("XAUUSDT", "XAU/USD"),
    "USTECH100": ("USTEC", "NAS100")
}

# Кнопки
keyboard = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
    [KeyboardButton(text="🔄 Получить сигнал")],
    [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
    [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
    [KeyboardButton(text="🕒 Статус"), KeyboardButton(text="📊 Стратегия")]
])

# Получение свечей с Binance
def get_binance_data(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=100"
    r = requests.get(url)
    df = pd.DataFrame(r.json())[[0, 1, 2, 3, 4]]
    df.columns = ['time', 'open', 'high', 'low', 'close']
    df['close'] = df['close'].astype(float)
    return df

# Получение данных с TwelveData
def get_twelve_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&apikey={TWELVEDATA_API_KEY}&outputsize=100"
    r = requests.get(url).json()
    df = pd.DataFrame(r['values'])[['datetime', 'close']]
    df['close'] = df['close'].astype(float)
    df = df[::-1].reset_index(drop=True)
    return df

# Усреднение двух источников
def get_combined_data(asset_key):
    if asset_key == "USTECH100":
        return get_twelve_data("NAS100")
    binance_symbol, twelvedata_symbol = ASSETS[asset_key][0], ASSETS[asset_key][1]
    df1 = get_binance_data(binance_symbol)
    df2 = get_twelve_data(twelvedata_symbol)
    df = df1.copy()
    df['close'] = (df1['close'] + df2['close']) / 2
    return df

# Стратегия MA + RSI + MACD
def analyze(df):
    df['ma10'] = df['close'].rolling(window=10).mean()
    df['ma50'] = df['close'].rolling(window=50).mean()
    df['rsi'] = compute_rsi(df['close'], 14)
    macd, signal = compute_macd(df['close'])
    df['macd'] = macd
    df['macd_signal'] = signal

    latest = df.iloc[-1]
    agree = 0
    if latest['ma10'] > latest['ma50']:
        agree += 1
    if latest['rsi'] < 30:
        agree += 1
    if latest['macd'] > latest['macd_signal']:
        agree += 1

    direction = "Buy" if agree >= 2 else "Sell"
    precision = 80 if agree == 3 else (66 if agree == 2 else 50)
    return {
        "direction": direction,
        "precision": precision,
        "agree": agree,
        "price": latest['close'],
        "tp": latest['close'] * (1.03 if direction == "Buy" else 0.97),
        "sl": latest['close'] * (0.97 if direction == "Buy" else 1.03)
    }

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=period).mean()
    avg_loss = pd.Series(loss).rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_macd(series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

@dp.message()
async def handler(msg: types.Message):
    user_id = msg.from_user.id
    text = msg.text
    user_data.setdefault(user_id, {"asset": "BTCUSD"})
    mute_status.setdefault(user_id, False)

    if text == "/start":
        await msg.answer("Пора выбраться из матрицы", reply_markup=keyboard)
    elif text in ASSETS:
        user_data[user_id]['asset'] = text
        await msg.answer(f"Актив выбран: {text}")
    elif text == "🔕 Mute":
        mute_status[user_id] = True
        await msg.answer("🔕 Уведомления отключены")
    elif text == "🔔 Unmute":
        mute_status[user_id] = False
        await msg.answer("🔔 Уведомления включены")
    elif text == "🕒 Статус":
        await msg.answer("Расписание: круглосуточно")
    elif text == "📊 Стратегия":
        await msg.answer("Стратегия: MA + RSI + MACD")
    elif text == "🔄 Получить сигнал":
        asset = user_data[user_id]["asset"]
        try:
            df = get_combined_data(asset)
            signal = analyze(df)
            precision = signal['precision']
            if precision < 60:
                return await msg.answer(f"⚠️ Риск велик, не время торговли (точность: {precision}%)")
            if precision >= 65:
                text = f"""📡 Сигнал по {asset}
Направление: {signal['direction']}
Цена входа: {signal['price']:.2f}
🎯 TP: {signal['tp']:.2f} ({'3%'})
🛡 SL: {signal['sl']:.2f} ({'3%'})
🎯 Точность: {signal['precision']}%
✅ Индикаторы: {signal['agree']}/3
"""
                await msg.answer(text, disable_notification=mute_status[user_id])
        except Exception as e:
            await msg.answer(f"Ошибка анализа: {e}")

# Запуск
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
