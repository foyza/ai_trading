import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums.parse_mode import ParseMode
import pandas as pd
from binance import Client
import requests
import numpy as np

# ==== Константы ====
API_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
TWELVE_DATA_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'
ASSETS = {
    "BTCUSD": ("BTCUSDT", "BTC/USD"),
    "XAUUSD": ("XAUUSDT", "XAU/USD"),
    "USTECH100": (None, "NAS100"),
}

user_state = {}
user_schedule = {}

# ==== Telegram-кнопки ====
main_kb = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
    [KeyboardButton(text="🔄 Получить сигнал")],
    [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
    [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
    [KeyboardButton(text="📊 Статус")]
])

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ==== Binance API без ключа ====
client = Client()

# ==== Получение данных ====
def get_binance_data(symbol):
    klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=100)
    df = pd.DataFrame(klines, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'trades', 'tb_base_vol', 'tb_quote_vol', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    return df[['close']]

def get_twelve_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=100&apikey={TWELVE_DATA_KEY}"
    r = requests.get(url).json()
    if "values" not in r:
        return pd.DataFrame({"close": []})
    df = pd.DataFrame(r['values'])
    df['close'] = df['close'].astype(float)
    return df[['close']]

def get_combined_data(asset_key):
    if asset_key == "USTECH100":
        return get_twelve_data("NAS100")
    binance_symbol, tw_symbol = ASSETS[asset_key]
    df1 = get_binance_data(binance_symbol)
    df2 = get_twelve_data(tw_symbol)

    min_len = min(len(df1), len(df2))
    df1 = df1.tail(min_len).reset_index(drop=True)
    df2 = df2.tail(min_len).reset_index(drop=True)

    df = df1.copy()
    df['close'] = (df1['close'] + df2['close']) / 2
    return df

# ==== Индикаторы ====
def calculate_indicators(df):
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['rsi'] = compute_rsi(df['close'], 14)
    df['macd'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    df['signal'] = df['macd'].ewm(span=9).mean()
    return df

def compute_rsi(series, period=14):
    delta = series.diff()
    up = np.where(delta > 0, delta, 0)
    down = np.where(delta < 0, -delta, 0)
    roll_up = pd.Series(up).rolling(window=period).mean()
    roll_down = pd.Series(down).rolling(window=period).mean()
    rs = roll_up / roll_down
    return 100 - (100 / (1 + rs))

# ==== Анализ сигнала ====
def analyze_signal(df):
    last = df.iloc[-1]
    ind = 0
    if last['ma10'] > last['ma50']:
        ind += 1
    if last['rsi'] > 55:
        ind += 1
    if last['macd'] > last['signal']:
        ind += 1

    if ind == 3:
        direction = "Buy"
        accuracy = 80
    elif ind == 0:
        direction = "Sell"
        accuracy = 80
    elif ind == 2:
        return "ind: 2/3 — недостаточно точный сигнал", 60, None, None, None
    else:
        return "⚠️ Риск велик, не время торговли", 50, None, None, None

    price = last['close']
    tp = price * 1.01 if direction == "Buy" else price * 0.99
    sl = price * 0.99 if direction == "Buy" else price * 1.01
    return direction, accuracy, price, tp, sl

# ==== Проверка расписания ====
def check_schedule(user_id):
    schedule = user_schedule.get(user_id)
    if not schedule:
        return True  # По умолчанию круглосуточно
    from datetime import datetime
    now = datetime.now()
    weekday = now.strftime('%A')
    if weekday not in schedule:
        return False
    start, end = schedule[weekday]
    return start <= now.hour < end
# ==== Команды и кнопки ====
@dp.message(F.text == "/start")
async def start(message: types.Message):
    user_state[message.from_user.id] = "BTCUSD"
    await message.answer("Пора выбраться из матрицы", reply_markup=main_kb)

@dp.message(F.text.in_(["BTCUSD", "XAUUSD", "USTECH100"]))
async def asset_select(message: types.Message):
    user_state[message.from_user.id] = message.text
    await message.answer(f"Актив переключён на {message.text}")

@dp.message(F.text == "🔄 Получить сигнал")
async def handle_signal(message: types.Message):
    user_id = message.from_user.id
    asset = user_state.get(user_id, "BTCUSD")
    if not check_schedule(user_id):
        await message.answer("⏰ Вне торгового времени")
        return
    df = get_combined_data(asset)
    df = calculate_indicators(df)
    direction, acc, price, tp, sl = analyze_signal(df)
    if acc >= 65:
        if acc >= 70:
            alert = "🚨 <b>AI сигнал</b>"
        else:
            alert = "🔍 <b>Ручной сигнал</b>"
        await message.answer(
            f"{alert}\n\n"
            f"📈 Актив: <b>{asset}</b>\n"
            f"📊 Точность: <b>{acc}%</b>\n"
            f"📉 Направление: <b>{direction}</b>\n"
            f"💰 Цена входа: <b>{round(price, 2)}</b>\n"
            f"🎯 TP: <b>{round(tp, 2)}</b> ({round(abs(tp - price) / price * 100, 2)}%)\n"
            f"🛑 SL: <b>{round(sl, 2)}</b> ({round(abs(sl - price) / price * 100, 2)}%)"
        )
    else:
        await message.answer(f"⚠️ Риск велик, не время торговли (точность: {acc}%)")

@dp.message(F.text == "📊 Статус")
async def status(message: types.Message):
    uid = message.from_user.id
    schedule = user_schedule.get(uid)
    if not schedule:
        await message.answer("🕒 Расписание: КРУГЛОСУТОЧНО, все дни")
    else:
        txt = "🕒 <b>Расписание:</b>\n"
        for day, (start, end) in schedule.items():
            txt += f"• {day}: {start}:00–{end}:00\n"
        await message.answer(txt)

@dp.message(F.text == "🔕 Mute")
async def mute(message: types.Message):
    await message.answer("🔕 Звук отключен (не реализовано)")

@dp.message(F.text == "🔔 Unmute")
async def unmute(message: types.Message):
    await message.answer("🔔 Звук включен (не реализовано)")

# ==== Запуск ====
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
