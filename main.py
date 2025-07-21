import logging
import pandas as pd
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime
import aiohttp

API_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
TWELVE_API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Словари
user_assets = {}
user_mute = {}
strategy = 'ma_rsi_macd'  # Пока одна стратегия
assets = {
    'BTCUSD': 'BTC/USD',
    'XAUUSD': 'XAU/USD',
    'USTECH100': 'NDX/USD'
}

# Кнопки
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
        [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")]
    ],
    resize_keyboard=True
)

# Логгер
logging.basicConfig(level=logging.INFO)

# === Получение данных из TwelveData ===
async def fetch_data_twelvedata(symbol):
    interval = '15min'
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey={TWELVE_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            try:
                df = pd.DataFrame(data['values'])
                df = df.iloc[::-1].reset_index(drop=True)
                df['close'] = df['close'].astype(float)
                return df
            except:
                return None

# === Стратегия на MA10/MA50 + RSI + MACD ===
def analyze(df):
    if df is None or len(df) < 50:
        return {'signal': None, 'accuracy': 0}

    df['MA10'] = df['close'].rolling(window=10).mean()
    df['MA50'] = df['close'].rolling(window=50).mean()
    df['EMA12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    last = df.iloc[-1]

    signals = {
        'ma': 'Buy' if last['MA10'] > last['MA50'] else 'Sell',
        'macd': 'Buy' if last['MACD'] > last['Signal'] else 'Sell',
        'rsi': 'Buy' if last['RSI'] < 30 else 'Sell' if last['RSI'] > 70 else 'Neutral'
    }

    agree = list(signals.values()).count('Buy') if 'Buy' in signals.values() else list(signals.values()).count('Sell')
    final_signal = 'Buy' if list(signals.values()).count('Buy') >= 2 else 'Sell' if list(signals.values()).count('Sell') >= 2 else None
    accuracy = 80 if agree == 3 else 70 if agree == 2 else 50

    return {
        'signal': final_signal,
        'accuracy': accuracy,
        'entry': round(last['close'], 2),
        'tp': round(last['close'] * (1.02 if final_signal == 'Buy' else 0.98), 2),
        'sl': round(last['close'] * (0.98 if final_signal == 'Buy' else 1.02), 2),
        'indicators': f"ind: {agree}/3"
    }

# === Отправка сигнала ===
async def send_signal(user_id, asset):
    symbol = assets.get(asset)
    df = await fetch_data_twelvedata(symbol)
    result = analyze(df)

    if result['accuracy'] >= 70:
        msg = (
            f"📊 Сигнал ({asset})\n"
            f"▶️ Направление: {result['signal']}\n"
            f"🎯 Вход: {result['entry']}\n"
            f"✅ TP: {result['tp']} ({'2%'})\n"
            f"🛑 SL: {result['sl']} ({'2%'})\n"
            f"📈 Точность: {result['accuracy']}%\n"
            f"{result['indicators']}"
        )
        disable_notification = user_mute.get(user_id, False)
        await bot.send_message(user_id, msg, disable_notification=disable_notification)
    elif result['accuracy'] < 60:
        await bot.send_message(user_id, f"⚠️ Риск велик, не время торговли (точность: {result['accuracy']}%)")

# === Хендлеры ===
@dp.message(commands=["start"])
async def cmd_start(msg: types.Message):
    user_assets[msg.from_user.id] = "BTCUSD"
    user_mute[msg.from_user.id] = False
    await msg.answer("Пора выбраться из матрицы", reply_markup=keyboard)

@dp.message()
async def handle_message(msg: types.Message):
    text = msg.text
    uid = msg.from_user.id

    if text in assets:
        user_assets[uid] = text
        await msg.answer(f"✅ Актив выбран: {text}")
    elif text == "🔄 Получить сигнал":
        asset = user_assets.get(uid, "BTCUSD")
        await send_signal(uid, asset)
    elif text == "🔕 Mute":
        user_mute[uid] = True
        await msg.answer("🔕 Уведомления отключены")
    elif text == "🔔 Unmute":
        user_mute[uid] = False
        await msg.answer("🔔 Уведомления включены")
    else:
        await msg.answer("Выберите действие с клавиатуры")

# === Запуск ===
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
