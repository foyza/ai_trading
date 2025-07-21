import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder
import pandas as pd
import numpy as np
import aiohttp
from ta.trend import MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator

# 🔐 Токен Telegram бота и TwelveData API
BOT_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVE_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"

# 🎯 Активы
ASSETS = {
    "BTCUSD": "BTC/USD",
    "XAUUSD": "XAU/USD",
    "USTECH100": "NDX"
}

# 📦 Состояния
user_data = {}

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()


# ✅ Клавиатура
def get_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🔄 Получить сигнал")
    kb.button(text="BTCUSD")
    kb.button(text="XAUUSD")
    kb.button(text="USTECH100")
    kb.button(text="🔕 Mute")
    kb.button(text="🔔 Unmute")
    kb.button(text="🎯 Стратегия: MA+RSI+MACD")
    return kb.as_markup(resize_keyboard=True)


# ✅ Получение OHLC данных
async def fetch_data(symbol: str):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=100&apikey={TWELVE_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            data = await r.json()
            if 'values' not in data:
                return None
            df = pd.DataFrame(data['values'])
            df = df.rename(columns={"datetime": "time"})
            df["time"] = pd.to_datetime(df["time"])
            df = df.sort_values("time")
            df.set_index("time", inplace=True)
            df = df.astype(float)
            return df


# ✅ Основной индикатор
def get_signal(df: pd.DataFrame, strategy: str):
    close = df['close']
    ma10 = close.rolling(window=10).mean()
    ma50 = close.rolling(window=50).mean()
    macd = MACD(close).macd_diff()
    rsi = RSIIndicator(close).rsi()

    agree = 0
    signal = "Hold"

    if ma10.iloc[-1] > ma50.iloc[-1]:
        agree += 1
    if macd.iloc[-1] > 0:
        agree += 1
    if rsi.iloc[-1] > 50:
        agree += 1

    if agree == 3:
        signal = "Buy"
        confidence = 75
    elif agree == 0:
        signal = "Sell"
        confidence = 75
    elif agree == 2:
        signal = "ind: 2/3"
        confidence = 65
    else:
        signal = "Hold"
        confidence = 50

    price = close.iloc[-1]
    tp = price * 1.02
    sl = price * 0.98

    return {
        "direction": signal,
        "confidence": confidence,
        "entry": round(price, 2),
        "tp_price": round(tp, 2),
        "sl_price": round(sl, 2),
        "tp_pct": "2%",
        "sl_pct": "2%"
    }


# ✅ Старт
@dp.message(CommandStart())
async def start(message: Message):
    user_data[message.from_user.id] = {"asset": "BTCUSD", "muted": False, "strategy": "MA+RSI+MACD"}
    await message.answer("Пора выбраться из матрицы", reply_markup=get_keyboard())


# ✅ Обработка всех сообщений
@dp.message(F.text)
async def handle_message(message: Message):
    uid = message.from_user.id
    text = message.text.strip()

    if uid not in user_data:
        user_data[uid] = {"asset": "BTCUSD", "muted": False, "strategy": "MA+RSI+MACD"}

    if text in ASSETS:
        user_data[uid]["asset"] = text
        await message.answer(f"Актив установлен: {text}")
        return

    if text == "🔄 Получить сигнал":
        await send_signal(message, uid, manual=True)
        return

    if text == "🔕 Mute":
        user_data[uid]["muted"] = True
        await message.answer("🔕 Уведомления выключены")
        return

    if text == "🔔 Unmute":
        user_data[uid]["muted"] = False
        await message.answer("🔔 Уведомления включены")
        return

    if "🎯 Стратегия" in text:
        user_data[uid]["strategy"] = "MA+RSI+MACD"
        await message.answer("Стратегия установлена: MA+RSI+MACD")
        return


# ✅ Отправка сигнала
async def send_signal(message: Message, uid: int, manual=False):
    asset = user_data[uid]["asset"]
    df = await fetch_data(asset)
    if df is None or df.empty:
        await message.answer("❌ Ошибка получения данных.")
        return

    strategy = user_data[uid]["strategy"]
    signal = get_signal(df, strategy)
    confidence = signal["confidence"]

    if manual and confidence < 65:
        await message.answer(f"⚠️ Риск велик, не время торговли (точность: {confidence}%)")
        return

    if not manual and confidence < 70:
        return  # не отправляем авто-сигнал

    direction = signal["direction"]
    entry = signal["entry"]
    tp_price = signal["tp_price"]
    sl_price = signal["sl_price"]
    tp_pct = signal["tp_pct"]
    sl_pct = signal["sl_pct"]

    msg = f"""📡 <b>Новый сигнал по {asset}</b>
<b>Направление:</b> {direction}
<b>Цена входа:</b> {entry}
<b>🎯 TP:</b> {tp_pct} → {tp_price}
<b>🛑 SL:</b> {sl_pct} → {sl_price}
<b>📈 Точность:</b> {confidence}%
"""
    await message.answer(msg, disable_notification=user_data[uid]["muted"])


# 🔁 Авто-сигналы каждые 2 мин
async def auto_signal_loop():
    while True:
        for uid in user_data:
            chat = user_data[uid]
            df = await fetch_data(chat["asset"])
            if df is None:
                continue
            signal = get_signal(df, chat["strategy"])
            if signal["confidence"] >= 70:
                try:
                    await bot.send_message(
                        uid,
                        f"""📡 <b>Авто сигнал по {chat["asset"]}</b>
<b>Направление:</b> {signal["direction"]}
<b>Цена входа:</b> {signal["entry"]}
<b>🎯 TP:</b> {signal["tp_pct"]} → {signal["tp_price"]}
<b>🛑 SL:</b> {signal["sl_pct"]} → {signal["sl_price"]}
<b>📈 Точность:</b> {signal["confidence"]}%
""",
                        disable_notification=chat["muted"]
                    )
                except:
                    pass
        await asyncio.sleep(120)  # каждые 2 мин


# ▶️ Запуск
async def main():
    loop.create_task(auto_signal_loop())
    await dp.start_polling(bot)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
