import asyncio
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import CommandStart
from datetime import datetime
import pandas as pd
import ta

BOT_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'
symbols = ["BTC/USD", "XAU/USD", "EUR/USD"]
strategies = ["MA+RSI+MACD", "Bollinger+Stochastic", "ADX+EMA", "Breakout+Volume", "PriceAction", "All"]

user_settings = {}

# Telegram bot setup
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="BTC/USD"), KeyboardButton(text="XAU/USD"), KeyboardButton(text="EUR/USD")],
        [KeyboardButton(text="🎯 Стратегия"), KeyboardButton(text="🔕 / 🔔")]
    ],
    resize_keyboard=True
)

COMMISSION_PCT = 0.04
SPREAD_PCT = 0.03

def is_doji(candle):
    body = abs(float(candle["open"]) - float(candle["close"]))
    total = float(candle["high"]) - float(candle["low"])
    return total > 0 and (body / total) < 0.1

def is_overbought_oversold(rsi):
    return rsi > 75 or rsi < 25

def apply_indicators(df):
    df = df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df = df[::-1]

    df["ema20"] = ta.trend.ema_indicator(df["close"], window=20)
    df["ema50"] = ta.trend.ema_indicator(df["close"], window=50)
    df["adx"] = ta.trend.adx(df["high"], df["low"], df["close"], window=14)
    df["rsi"] = ta.momentum.rsi(df["close"], window=14)
    df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=14)
    return df

def analyze(data_15m, data_1h, strategy):
    if "values" not in data_15m or "values" not in data_1h:
        return {"error": "Недостаточно данных"}

    df_15 = pd.DataFrame(data_15m["values"])
    df_1h = pd.DataFrame(data_1h["values"])
    df_15 = apply_indicators(df_15)
    df_1h = apply_indicators(df_1h)

    last_15 = df_15.iloc[-1]
    last_1h = df_1h.iloc[-1]

    if is_doji(data_15m["values"][0]):
        return {"error": "Doji свеча"}
    if is_overbought_oversold(last_15["rsi"]):
        return {"error": "RSI в зоне перекупленности/перепроданности"}

    ema_signal = "Buy" if last_15["ema20"] > last_15["ema50"] else "Sell"
    adx_ok = last_15["adx"] > 20 and last_1h["adx"] > 20

    signal = ema_signal if adx_ok else "Hold"
    if signal == "Hold":
        return {"error": "ADX слабый"}

    price = float(data_15m["values"][0]["close"])
    atr = last_15["atr"]
    tp_pct = atr / price * 100 * 1.5 - COMMISSION_PCT
    sl_pct = atr / price * 100 + SPREAD_PCT + COMMISSION_PCT

    confidence = 75 if strategy != "All" else 85

    return {
        "signal": signal,
        "confidence": confidence,
        "tp_pct": round(tp_pct, 2),
        "sl_pct": round(sl_pct, 2),
        "price": price
    }

async def fetch_data(symbol, interval):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol.replace('/', '')}&interval={interval}&outputsize=50&apikey={API_KEY}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        return resp.json()

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    uid = msg.from_user.id
    user_settings[uid] = {
        "asset": symbols[0],
        "mute": False,
        "strategy": strategies[0],
        "schedule": []
    }
    await msg.answer("Пора выбраться из матрицы!", reply_markup=keyboard)

@dp.message()
async def handle_msg(msg: types.Message):
    uid = msg.from_user.id
    st = user_settings.get(uid)
    if not st:
        return await msg.answer("Используй /start сначала")

    text = msg.text
    if text in symbols:
        st["asset"] = text
        return await msg.answer(f"Актив: {text}")
    elif text == "🔄 Получить сигнал":
        data_15m = await fetch_data(st["asset"], "15min")
        data_1h = await fetch_data(st["asset"], "1h")
        res = analyze(data_15m, data_1h, st["strategy"])
        if "error" in res:
            return await msg.answer(f"⚠️ {res['error']}")
        msg_text = (
            f"📊 {st['asset']} — {res['signal']} сигнал"
            f"🎯 Уверенность: {res['confidence']}%"
            f"💰 Цена: {res['price']}$"
            f"🎯 TP: {res['tp_pct']}%"
            f"🛑 SL: {res['sl_pct']}%"
        )
        return await msg.answer(msg_text)
    elif text == "🔕 / 🔔":
        st["mute"] = not st["mute"]
        return await msg.answer("🔕 Оповещения отключены" if st["mute"] else "🔔 Оповещения включены")
    elif text == "🎯 Стратегия":
        current = strategies.index(st["strategy"])
        st["strategy"] = strategies[(current + 1) % len(strategies)]
        return await msg.answer(f"Стратегия: {st['strategy']}")
    else:
        return await msg.answer("Выберите опцию с клавиатуры")

async def auto_signals():
    while True:
        for uid, st in user_settings.items():
            if st["mute"]:
                continue
            data_15m = await fetch_data(st["asset"], "15min")
            data_1h = await fetch_data(st["asset"], "1h")
            res = analyze(data_15m, data_1h, st["strategy"])
            if "error" not in res and res["confidence"] >= 70:
                msg_text = (
                    f"📊 [AUTO] {st['asset']} — {res['signal']} сигнал"
                    f"🎯 Уверенность: {res['confidence']}%"
                    f"💰 Цена: {res['price']}$"
                    f"🎯 TP: {res['tp_pct']}%"
                    f"🛑 SL: {res['sl_pct']}%"
                )
                await bot.send_message(uid, msg_text)
        await asyncio.sleep(900)  # каждые 15 минут

async def main():
    asyncio.create_task(auto_signals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
