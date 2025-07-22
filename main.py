import asyncio
import httpx
import numpy as np
import pandas as pd
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import CommandStart
from datetime import datetime

BOT_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

user_settings = {}
symbols = ["BTC/USD", "XAU/USD", "EUR/USD"]
strategies = ["MA+RSI+MACD", "Bollinger+Stochastic"]

def get_main_keyboard():
    buttons = [
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text=s.replace("/", "") ) for s in symbols],
        [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
        [KeyboardButton(text="🎯 Стратегия")],
        [KeyboardButton(text="🕒 Расписание")],
        [KeyboardButton(text="📊 Статус")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

async def fetch_data(symbol, interval="15min"):
    params = {"symbol": symbol, "interval": interval, "outputsize": 100, "apikey": API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://api.twelvedata.com/time_series", params=params)
    return r.json()

def is_doji(open_, close, high, low):
    body = abs(close - open_)
    range_ = high - low
    return body / range_ < 0.1

def analyze(data, strategy):
    if "values" not in data or not data["values"]:
        return {"error": data.get("message", "Нет данных")}

    df = pd.DataFrame(data["values"])
    df = df.iloc[::-1]  # обратный порядок
    df = df.astype(float)
    df["timestamp"] = pd.to_datetime(data["values"][0]["datetime"])
    
    # Индикаторы
    df["ema"] = EMAIndicator(df["close"], window=200).ema_indicator()
    adx = ADXIndicator(df["high"], df["low"], df["close"])
    df["adx"] = adx.adx()
    df["rsi"] = RSIIndicator(df["close"]).rsi()
    atr = AverageTrueRange(df["high"], df["low"], df["close"])
    df["atr"] = atr.average_true_range()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # Фильтры
    if latest["close"] < latest["ema"]: return {"filter": "Цена ниже EMA200"}
    if latest["adx"] < 20: return {"filter": "ADX < 20, тренд слабый"}
    if is_doji(latest["open"], latest["close"], latest["high"], latest["low"]): return {"filter": "Doji свеча"}
    if latest["rsi"] > 70 or latest["rsi"] < 30: return {"filter": "RSI в зоне перегрева"}

    signal = "Buy" if latest["close"] > prev["close"] else "Sell"
    confidence = 80 if latest["adx"] > 25 else 70

    tp_points = round(latest["atr"] * 1.5, 4)
    sl_points = round(latest["atr"] * 1.0, 4)

    spread = latest["close"] * 0.0003  # 3 пункта спред
    fee = latest["close"] * 0.001  # комиссия 0.1%
    correction = spread + fee

    if signal == "Buy":
        tp = round(latest["close"] + tp_points - correction, 4)
        sl = round(latest["close"] - sl_points - correction, 4)
    else:
        tp = round(latest["close"] - tp_points + correction, 4)
        sl = round(latest["close"] + sl_points + correction, 4)

    return {
        "price": round(latest["close"], 4),
        "signal": signal,
        "tp": tp,
        "sl": sl,
        "confidence": confidence
    }

async def analyze_dual_tf(symbol, strategy):
    data_15 = await fetch_data(symbol, interval="15min")
    data_60 = await fetch_data(symbol, interval="1h")

    result_15 = analyze(data_15, strategy)
    result_60 = analyze(data_60, strategy)

    if "signal" in result_15 and "signal" in result_60:
        if result_15["signal"] == result_60["signal"]:
            return result_15
        else:
            return {"filter": "M15 и H1 не совпадают"}
    return result_15 if "signal" in result_15 else result_60

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    uid = msg.from_user.id
    user_settings[uid] = {"asset": symbols[0], "mute": False, "strategy": strategies[0], "schedule": []}
    await msg.answer("Пора выбраться из матрицы", reply_markup=get_main_keyboard())

@dp.message(lambda msg: msg.text == "🔄 Получить сигнал")
async def get_signal(msg: types.Message):
    uid = msg.from_user.id
    settings = user_settings.get(uid, {})
    symbol = settings.get("asset", symbols[0])
    strategy = settings.get("strategy", strategies[0])
    result = await analyze_dual_tf(symbol, strategy)

    if "signal" in result:
        text = (f"📈 Актив: {symbol}\n📊 Сигнал: {result['signal']}\n"
                f"🎯 Цена: {result['price']}\n🎯 TP: {result['tp']}\n🛑 SL: {result['sl']}\n"
                f"📈 Уверенность: {result['confidence']}%")
    elif "filter" in result:
        text = f"⚠️ Фильтр: {result['filter']}"
    else:
        text = f"❌ Ошибка: {result.get('error', 'Не удалось получить данные')}"
    await msg.answer(text)

@dp.message(lambda msg: msg.text in [s.replace("/", "") for s in symbols])
async def set_asset(msg: types.Message):
    uid = msg.from_user.id
    asset = msg.text
    for s in symbols:
        if asset in s.replace("/", ""):
            user_settings[uid]["asset"] = s
            await msg.answer(f"🪙 Актив установлен: {s}")

@dp.message(lambda msg: msg.text == "🔕 Mute")
async def mute_user(msg: types.Message):
    user_settings[msg.from_user.id]["mute"] = True
    await msg.answer("🔇 Автосигналы отключены")

@dp.message(lambda msg: msg.text == "🔔 Unmute")
async def unmute_user(msg: types.Message):
    user_settings[msg.from_user.id]["mute"] = False
    await msg.answer("🔊 Автосигналы включены")

async def auto_signal_loop():
    while True:
        for uid, config in user_settings.items():
            if config.get("mute", False): continue
            result = await analyze_dual_tf(config["asset"], config["strategy"])
            if "signal" in result and result["confidence"] >= 70:
                try:
                    await bot.send_message(uid,
                        f"📢 [AUTO]\n📈 {config['asset']}\n📊 {result['signal']}\n"
                        f"Цена: {result['price']} | TP: {result['tp']} | SL: {result['sl']}\n"
                        f"Уверенность: {result['confidence']}%")
                except:
                    pass
        await asyncio.sleep(900)  # 15 мин

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(auto_signal_loop())
    loop.run_until_complete(main())
    
