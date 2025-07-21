import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
import numpy as np
import pandas as pd

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVEDATA_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"
ASSETS = ['BTC/USD', 'XAU/USD', 'NDX']

# Добавлен словарь для соответствия активов символам TwelveData API
TWELVE_SYMBOLS = {
    'BTC/USD': 'BTC/USD',
    'XAU/USD': 'XAU/USD', 
    'NDX': 'NDX'
}

dp = Dispatcher()
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
logging.basicConfig(level=logging.INFO)

# Память пользователей
user_settings = {}  # {user_id: {"asset": ..., "muted": False, "strategy": ..., ...}}

# Клавиатура
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Получить сигнал")],
            [KeyboardButton(text="BTC/USD"), KeyboardButton(text="XAU/USD"), KeyboardButton(text="NDX")],
            [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
            [KeyboardButton(text="🎯 Стратегия"), KeyboardButton(text="🕒 Расписание")],
            [KeyboardButton(text="📊 Статус")]
        ],
        resize_keyboard=True
    )

# Получение OHLCV данных от TwelveData
async def get_twelvedata(asset):
    symbol = TWELVE_SYMBOLS.get(asset)
    if not symbol:
        raise ValueError(f"Неизвестный актив для TwelveData: {asset}")
    
    url = f"https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": 50,
        "apikey": TWELVEDATA_API_KEY,  # Используем константу вместо хардкода
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()
                if "values" not in data:
                    logging.error(f"TwelveData API error: {data}")
                    raise ValueError(f"TwelveData API вернул ошибку: {data.get('message', 'нет данных')}")
                
                df = pd.DataFrame(data["values"])
                df["datetime"] = pd.to_datetime(df["datetime"])
                # Конвертируем числовые колонки в float
                numeric_columns = ["open", "high", "low", "close", "volume"]
                for col in numeric_columns:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                df = df.sort_values("datetime")
                return df
    except Exception as e:
        logging.error(f"Error fetching data for {asset}: {e}")
        return None

# Стратегия: MA + RSI + MACD
def analyze(df):
    if len(df) < 50:
        return "neutral", 0, 0
    
    # Убеждаемся, что close - это числовая колонка
    df["close"] = pd.to_numeric(df["close"], errors='coerce')
    
    df["ma10"] = df["close"].rolling(window=10).mean()
    df["ma50"] = df["close"].rolling(window=50).mean()
    df["rsi"] = compute_rsi(df["close"])
    df["macd"] = compute_macd(df["close"])

    latest = df.iloc[-1]
    
    # Проверяем на NaN значения
    if pd.isna(latest["ma10"]) or pd.isna(latest["ma50"]) or pd.isna(latest["rsi"]) or pd.isna(latest["macd"]):
        return "neutral", 0, latest["close"]
    
    ma_signal = "buy" if latest["ma10"] > latest["ma50"] else "sell"
    rsi_signal = "buy" if latest["rsi"] < 30 else "sell" if latest["rsi"] > 70 else "neutral"
    macd_signal = "buy" if latest["macd"] > 0 else "sell"

    signals = [ma_signal, rsi_signal, macd_signal]
    direction = "buy" if signals.count("buy") >= 2 else "sell" if signals.count("sell") >= 2 else "neutral"
    accuracy = int((signals.count(direction) / 3) * 100) if direction != "neutral" else int((2 / 3) * 100)

    return direction, accuracy, df["close"].iloc[-1]

def compute_rsi(series, period=14):
    if len(series) < period:
        return pd.Series([np.nan] * len(series), index=series.index)
    
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.rolling(window=period).mean()
    ma_down = down.rolling(window=period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def compute_macd(series):
    if len(series) < 26:
        return pd.Series([np.nan] * len(series), index=series.index)
    
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    return ema12 - ema26

# Отправка сигнала
async def send_signal(user_id, asset, manual=False):  # Добавлен параметр manual
    try:
        df = await get_twelvedata(asset)
        if df is None or len(df) < 50:
            await bot.send_message(user_id, f"⚠️ Не удалось получить данные по {asset}")
            return

        direction, accuracy, price = analyze(df)
        
        if accuracy < 60 and not manual:  # При ручном запросе показываем результат в любом случае
            await bot.send_message(user_id, f"⚠️ Риск велик, не время торговли (точность: {accuracy}%)")
            return
            
        if direction == "neutral":
            await bot.send_message(user_id, "⚠️ Недостаточно сигнала от индикаторов")
            return

        tp_pct, sl_pct = 2.0, 1.0
        tp_price = round(price * (1 + tp_pct / 100), 2) if direction == "buy" else round(price * (1 - tp_pct / 100), 2)
        sl_price = round(price * (1 - sl_pct / 100), 2) if direction == "buy" else round(price * (1 + sl_pct / 100), 2)

        msg = (
            f"📈 Актив: <b>{asset}</b>\n"
            f"📈 Сигнал: <b>{direction.upper()}</b>\n"
            f"🎯 Вход: <b>{price}</b>\n"
            f"🟢 TP: +{tp_pct}% → <b>{tp_price}</b>\n"
            f"🔴 SL: -{sl_pct}% → <b>{sl_price}</b>\n"
            f"📊 Точность: <b>{accuracy}%</b>"
        )
        mute = user_settings.get(user_id, {}).get("muted", False)
        await bot.send_message(user_id, msg, disable_notification=mute)
        
    except Exception as e:
        logging.error(f"Error in send_signal: {e}")
        await bot.send_message(user_id, f"❌ Ошибка при получении сигнала: {str(e)}")

# Команда /start
@dp.message(CommandStart())
async def start(message: types.Message):
    user_settings[message.from_user.id] = {"asset": "BTC/USD", "muted": False, "strategy": "ma+rsi+macd"}
    await message.answer("Пора выбраться из матрицы", reply_markup=get_main_keyboard())

# Обработка кнопок
@dp.message()
async def handle_buttons(message: types.Message):
    uid = message.from_user.id
    text = message.text
    if uid not in user_settings:
        user_settings[uid] = {"asset": "BTC/USD", "muted": False, "strategy": "ma+rsi+macd"}

    if text == "🔄 Получить сигнал":
        await send_signal(uid, user_settings[uid]["asset"], manual=True)
    elif text in ASSETS:
        user_settings[uid]["asset"] = text
        await message.answer(f"✅ Актив установлен: {text}")
    elif text == "🔕 Mute":
        user_settings[uid]["muted"] = True
        await message.answer("🔕 Уведомления отключены")
    elif text == "🔔 Unmute":
        user_settings[uid]["muted"] = False
        await message.answer("🔔 Уведомления включены")
    elif text == "🎯 Стратегия":
        await message.answer("Стратегия: MA + RSI + MACD (фиксировано)")
    elif text == "🕒 Расписание":
        await message.answer("Расписание: круглосуточно (настройка пока отключена)")
    elif text == "📊 Статус":
        asset = user_settings[uid]["asset"]
        mute = "🔕" if user_settings[uid]["muted"] else "🔔"
        strategy = user_settings[uid]["strategy"]
        await message.answer(f"📊 Текущий актив: {asset}\n🔔 Звук: {mute}\n🎯 Стратегия: {strategy}")

# Автоотправка (точность >70%)
async def auto_signal_loop():
    while True:
        try:
            for uid, settings in user_settings.items():
                try:
                    asset = settings["asset"]
                    df = await get_twelvedata(asset)
                    if df is None or len(df) < 50:
                        continue
                    direction, accuracy, _ = analyze(df)
                    if direction != "neutral" and accuracy >= 70:
                        await send_signal(uid, asset)
                except Exception as e:
                    logging.error(f"Error processing user {uid}: {e}")
                    continue
        except Exception as e:
            logging.error(f"Error in auto_signal_loop: {e}")
        
        await asyncio.sleep(300)  # каждые 5 минут

async def main():
    # Запускаем автосигналы в фоновой задаче
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
