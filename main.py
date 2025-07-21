import logging
import asyncio
import requests
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode

# === Настройки ===
BOT_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVE_DATA_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"
USELESS_THRESHOLD = 0.6
SIGNAL_THRESHOLD = 0.7

# === Логгинг и запуск ===
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
mute_users = set()
last_signals = {}

# === Клавиатура ===
def main_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="BTCUSDT"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="NAS100")],
        [KeyboardButton(text="🔇 Mute"), KeyboardButton(text="🔔 Unmute")]
    ], resize_keyboard=True)

# === Получение данных Binance ===
def get_binance_data(symbol='BTCUSDT', interval='15m', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url, timeout=10)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'trades', 'tb_base', 'tb_quote', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    return df[['time', 'close']]

# === Получение данных с TwelveData (только для NAS100) ===
def get_twelvedata(symbol='NAS100', interval='15min', apikey=TWELVE_DATA_API_KEY):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey={apikey}"
    response = requests.get(url, timeout=10).json()
    if 'values' not in response:
        return None
    df = pd.DataFrame(response['values'])
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['close'] = df['close'].astype(float)
    df = df.sort_values(by='datetime')
    return df[['datetime', 'close']].rename(columns={'datetime': 'time'})

# === Расчёт сигнала по MA10/MA50 ===
def calculate_ma_signal(df):
    df['MA10'] = df['close'].rolling(window=10).mean()
    df['MA50'] = df['close'].rolling(window=50).mean()

    if df['MA10'].iloc[-2] < df['MA50'].iloc[-2] and df['MA10'].iloc[-1] > df['MA50'].iloc[-1]:
        return 'Buy'
    elif df['MA10'].iloc[-2] > df['MA50'].iloc[-2] and df['MA10'].iloc[-1] < df['MA50'].iloc[-1]:
        return 'Sell'
    else:
        return None

# === Получить сигнал по активу ===
def get_signal(asset: str):
    try:
        if asset == 'NAS100':
            df = get_twelvedata(symbol='NAS100')
        else:
            df = get_binance_data(symbol=asset)
        if df is None or len(df) < 50:
            return None, "❌ Недостаточно данных для анализа"
        
        signal = calculate_ma_signal(df)
        if not signal:
            return None, "⚠️ Нет чёткого сигнала на данный момент"

        price = df['close'].iloc[-1]
        tp = round(price * 1.01, 2)
        sl = round(price * 0.99, 2)

        return signal, (
            f"<b>{asset}</b>\n"
            f"🔮 Сигнал: <b>{signal}</b>\n"
            f"🎯 Вход: <b>{price}</b>\n"
            f"✅ TP (1%): <b>{tp}</b>\n"
            f"🛑 SL (1%): <b>{sl}</b>"
        )
    except Exception as e:
        return None, f"❌ Ошибка: {e}"

# === Команды и обработка ===
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text == '/start':
        await message.answer("Пора выбраться из матрицы. Выбери актив или запроси сигнал:", reply_markup=main_keyboard())
        return

    if text == "🔇 Mute":
        mute_users.add(user_id)
        await message.answer("🔕 Уведомления отключены.")
        return

    if text == "🔔 Unmute":
        mute_users.discard(user_id)
        await message.answer("🔔 Уведомления включены.")
        return

    if text == "🔄 Получить сигнал":
        asset = last_signals.get(user_id, 'BTCUSDT')
        signal, msg = get_signal(asset)
        if signal:
            await message.answer(msg, disable_notification=(user_id in mute_users))
        else:
            await message.answer(msg)
        return

    if text in ['BTCUSDT', 'XAUUSD', 'NAS100']:
        last_signals[user_id] = text
        await message.answer(f"✅ Актив установлен: <b>{text}</b>")
        return

# === Автоматическая проверка сигналов (каждые 2 минуты) ===
async def auto_signal_loop():
    await bot.send_message(813631865, "✅ Автоматическая проверка сигналов запущена.")
    while True:
        for asset in ['BTCUSDT', 'XAUUSD', 'NAS100']:
            signal, msg = get_signal(asset)
            if signal:
                for user_id in last_signals:
                    await bot.send_message(user_id, msg, disable_notification=(user_id in mute_users))
        await asyncio.sleep(120)

# === Старт ===
async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
