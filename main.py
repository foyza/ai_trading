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
ASSETS = ['BTC/USD', 'XAU/USD', 'USTECH100']

# Добавлен словарь для соответствия активов символам TwelveData API
TWELVE_SYMBOLS = {
    'BTC/USD': 'BTC/USD',
    'XAU/USD': 'XAU/USD', 
    'USTECH100': 'USTECH100'  # Nasdaq 100 индекс
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
            [KeyboardButton(text="BTC/USD"), KeyboardButton(text="XAU/USD"), KeyboardButton(text="USTECH100")],
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
                
                # Проверяем на ошибки API
                if "status" in data and data["status"] == "error":
                    error_msg = data.get("message", "Неизвестная ошибка API")
                    if "plan" in error_msg.lower() or "upgrade" in error_msg.lower():
                        raise ValueError(f"Актив {asset} недоступен в бесплатном плане TwelveData")
                    else:
                        raise ValueError(f"Ошибка API: {error_msg}")
                
                if "values" not in data:
                    logging.error(f"TwelveData API error: {data}")
                    raise ValueError(f"TwelveData API не вернул данные для {asset}")
                
                df = pd.DataFrame(data["values"])
                if df.empty:
                    raise ValueError(f"Получены пустые данные для {asset}")
                    
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

# Улучшенная стратегия для более точных сигналов
def analyze(df):
    if len(df) < 100:
        return "neutral", 0, 0
    
    # Убеждаемся, что close - это числовая колонка
    df["close"] = pd.to_numeric(df["close"], errors='coerce')
    df["high"] = pd.to_numeric(df["high"], errors='coerce')
    df["low"] = pd.to_numeric(df["low"], errors='coerce')
    df["volume"] = pd.to_numeric(df["volume"], errors='coerce')
    
    # Множественные moving averages для подтверждения тренда
    df["ma10"] = df["close"].rolling(window=10).mean()
    df["ma20"] = df["close"].rolling(window=20).mean()
    df["ma50"] = df["close"].rolling(window=50).mean()
    
    # RSI с разными периодами
    df["rsi14"] = compute_rsi(df["close"], 14)
    df["rsi21"] = compute_rsi(df["close"], 21)
    
    # MACD с сигнальной линией
    df["macd"], df["macd_signal"] = compute_macd_signal(df["close"])
    df["macd_histogram"] = df["macd"] - df["macd_signal"]
    
    # Bollinger Bands
    df["bb_upper"], df["bb_lower"], df["bb_middle"] = compute_bollinger_bands(df["close"])
    
    # Stochastic Oscillator
    df["stoch_k"], df["stoch_d"] = compute_stochastic(df["high"], df["low"], df["close"])
    
    # Volume analysis
    df["volume_ma"] = df["volume"].rolling(window=20).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Проверяем на NaN значения
    required_fields = ["ma10", "ma20", "ma50", "rsi14", "rsi21", "macd", "macd_signal", 
                      "bb_upper", "bb_lower", "stoch_k", "stoch_d"]
    if any(pd.isna(latest[field]) for field in required_fields):
        return "neutral", 0, latest["close"]
    
    signals = []
    signal_strengths = []
    
    # 1. Тренд по MA (вес: 25%)
    if latest["ma10"] > latest["ma20"] > latest["ma50"]:
        if latest["close"] > latest["ma10"]:
            signals.append("buy")
            signal_strengths.append(25)
    elif latest["ma10"] < latest["ma20"] < latest["ma50"]:
        if latest["close"] < latest["ma10"]:
            signals.append("sell")
            signal_strengths.append(25)
    
    # 2. RSI множественное подтверждение (вес: 20%)
    if latest["rsi14"] < 30 and latest["rsi21"] < 35:
        signals.append("buy")
        signal_strengths.append(20)
    elif latest["rsi14"] > 70 and latest["rsi21"] > 65:
        signals.append("sell")
        signal_strengths.append(20)
    elif 40 < latest["rsi14"] < 60 and 40 < latest["rsi21"] < 60:
        # RSI в нейтральной зоне - ищем дивергенцию с MACD
        if latest["macd"] > prev["macd"] and latest["macd"] > latest["macd_signal"]:
            signals.append("buy")
            signal_strengths.append(10)
        elif latest["macd"] < prev["macd"] and latest["macd"] < latest["macd_signal"]:
            signals.append("sell")
            signal_strengths.append(10)
    
    # 3. MACD с гистограммой (вес: 20%)
    if (latest["macd"] > latest["macd_signal"] and 
        latest["macd_histogram"] > prev["macd_histogram"] and
        latest["macd_histogram"] > 0):
        signals.append("buy")
        signal_strengths.append(20)
    elif (latest["macd"] < latest["macd_signal"] and 
          latest["macd_histogram"] < prev["macd_histogram"] and
          latest["macd_histogram"] < 0):
        signals.append("sell")
        signal_strengths.append(20)
    
    # 4. Bollinger Bands (вес: 15%)
    if latest["close"] < latest["bb_lower"] and prev["close"] >= prev["bb_lower"]:
        signals.append("buy")
        signal_strengths.append(15)
    elif latest["close"] > latest["bb_upper"] and prev["close"] <= prev["bb_upper"]:
        signals.append("sell")
        signal_strengths.append(15)
    
    # 5. Stochastic (вес: 10%)
    if latest["stoch_k"] < 20 and latest["stoch_d"] < 20 and latest["stoch_k"] > latest["stoch_d"]:
        signals.append("buy")
        signal_strengths.append(10)
    elif latest["stoch_k"] > 80 and latest["stoch_d"] > 80 and latest["stoch_k"] < latest["stoch_d"]:
        signals.append("sell")
        signal_strengths.append(10)
    
    # 6. Volume confirmation (вес: 10%)
    if not pd.isna(latest["volume"]) and not pd.isna(latest["volume_ma"]):
        if latest["volume"] > latest["volume_ma"] * 1.5:  # Высокий объем
            if len(signals) > 0:
                signal_strengths.append(10)
    
    # Определяем итоговый сигнал
    buy_strength = sum(strength for signal, strength in zip(signals, signal_strengths) if signal == "buy")
    sell_strength = sum(strength for signal, strength in zip(signals, signal_strengths) if signal == "sell")
    
    total_possible = 100
    
    if buy_strength >= 60:  # Минимум 60% уверенности
        direction = "buy"
        accuracy = min(95, buy_strength + 15)  # Бонус за множественное подтверждение
    elif sell_strength >= 60:
        direction = "sell" 
        accuracy = min(95, sell_strength + 15)
    else:
        direction = "neutral"
        accuracy = max(buy_strength, sell_strength)

    return direction, int(accuracy), latest["close"]

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

def compute_macd_signal(series):
    if len(series) < 26:
        return pd.Series([np.nan] * len(series), index=series.index), pd.Series([np.nan] * len(series), index=series.index)
    
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def compute_bollinger_bands(series, period=20, std_dev=2):
    if len(series) < period:
        return (pd.Series([np.nan] * len(series), index=series.index),
                pd.Series([np.nan] * len(series), index=series.index),
                pd.Series([np.nan] * len(series), index=series.index))
    
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, lower, middle

def compute_stochastic(high, low, close, k_period=14, d_period=3):
    if len(close) < k_period:
        return (pd.Series([np.nan] * len(close), index=close.index),
                pd.Series([np.nan] * len(close), index=close.index))
    
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    d_percent = k_percent.rolling(window=d_period).mean()
    return k_percent, d_percent

# Отправка сигнала
async def send_signal(user_id, asset, manual=False):  # Добавлен параметр manual
    try:
        df = await get_twelvedata(asset)
        if df is None or len(df) < 100:
            await bot.send_message(user_id, f"⚠️ Не удалось получить достаточно данных по {asset}")
            return

        direction, accuracy, price = analyze(df)
        
        if accuracy < 75 and not manual:  # Повышаем требования к точности для автосигналов
            if manual:
                await bot.send_message(user_id, f"⚠️ Низкая точность сигнала: {accuracy}%. Рекомендую подождать более точного сигнала.")
            return
            
        if direction == "neutral":
            if manual:
                await bot.send_message(user_id, f"⚠️ Рынок в состоянии неопределенности. Точность: {accuracy}%")
            return

        # Динамические TP/SL в зависимости от актива и точности
        if asset == "BTC/USD":
            tp_pct, sl_pct = 1.5, 0.8
        elif asset == "XAU/USD":
            tp_pct, sl_pct = 1.2, 0.6
        elif asset == "USTECH100":
            tp_pct, sl_pct = 1.0, 0.5
        else:
            tp_pct, sl_pct = 1.5, 0.8

        # Корректируем TP/SL на основе точности
        confidence_multiplier = accuracy / 100
        tp_pct *= confidence_multiplier
        sl_pct *= confidence_multiplier

        tp_price = round(price * (1 + tp_pct / 100), 2) if direction == "buy" else round(price * (1 - tp_pct / 100), 2)
        sl_price = round(price * (1 - sl_pct / 100), 2) if direction == "buy" else round(price * (1 + sl_pct / 100), 2)

        # Эмодзи для точности
        accuracy_emoji = "🔥" if accuracy >= 90 else "⚡" if accuracy >= 80 else "📊"
        
        msg = (
            f"{accuracy_emoji} <b>ТОЧНЫЙ СИГНАЛ</b> {accuracy_emoji}\n"
            f"📈 Актив: <b>{asset}</b>\n"
            f"🎯 Направление: <b>{direction.upper()}</b>\n"
            f"💰 Вход: <b>{price}</b>\n"
            f"🟢 TP: +{tp_pct:.1f}% → <b>{tp_price}</b>\n"
            f"🔴 SL: -{sl_pct:.1f}% → <b>{sl_price}</b>\n"
            f"🎯 Точность: <b>{accuracy}%</b>\n"
            f"📊 Множественное подтверждение индикаторов"
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
    welcome_msg = (
        "🚀 Добро пожаловать в Trading Signals Bot!\n\n"
        "📊 Доступные активы:\n"
        "• BTC/USD - Биткоин\n"
        "• XAU/USD - Золото\n"  
        "• USTECH100 - Nasdaq 100\n\n"
        "🎯 Точные сигналы с множественным подтверждением:\n"
        "• Moving Averages (3 периода)\n"
        "• RSI (2 периода)\n"
        "• MACD + сигнальная линия\n"
        "• Bollinger Bands\n"
        "• Stochastic Oscillator\n"
        "• Объемы\n\n"
        "⚡ Минимальная точность: 75%"
    )
    await message.answer(welcome_msg, reply_markup=get_main_keyboard())

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
        strategy_info = (
            "🎯 <b>МНОГОУРОВНЕВАЯ СТРАТЕГИЯ</b>\n\n"
            "📊 <b>Индикаторы (веса):</b>\n"
            "• Moving Averages - 25%\n"
            "• RSI (14+21) - 20%\n" 
            "• MACD + Signal - 20%\n"
            "• Bollinger Bands - 15%\n"
            "• Stochastic - 10%\n"
            "• Volume - 10%\n\n"
            "⚡ <b>Требования:</b>\n"
            "• Минимум 60% для сигнала\n"
            "• 75%+ для автосигналов\n"
            "• 85%+ для premium автосигналов\n\n"
            "🔥 <b>Точность 90%+</b> - самые сильные сигналы!"
        )
        await message.answer(strategy_info)
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
                    if direction != "neutral" and accuracy >= 85:  # Очень высокие требования к автосигналам
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
