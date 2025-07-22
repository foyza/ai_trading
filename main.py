import asyncio, httpx
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import CommandStart
from datetime import datetime
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

BOT_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

user_settings = {}
symbols = ["BTC/USD", "XAU/USD", "EUR/USD"]
strategies = ["EMA+ADX+RSI"]

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

async def fetch_data(symbol, interval="15min", size=100):
    params = {"symbol": symbol, "interval": interval, "outputsize": size, "apikey": API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://api.twelvedata.com/time_series", params=params)
    return r.json()

def is_doji(candle):
    body = abs(float(candle["open"]) - float(candle["close"]))
    range_ = float(candle["high"]) - float(candle["low"])
    return body < 0.1 * range_

def preprocess(data):
    df = pd.DataFrame(data["values"])
    df = df.iloc[::-1].copy()
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)
    return df

def analyze_combined(m15, h1):
    df_m15 = preprocess(m15)
    df_h1 = preprocess(h1)

    df = df_m15.copy()
    df["ema"] = EMAIndicator(df["close"], window=20).ema_indicator()
    df["adx"] = ADXIndicator(df["high"], df["low"], df["close"]).adx()
    df["rsi"] = RSIIndicator(df["close"]).rsi()
    df["atr"] = AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range()

    latest = df.iloc[-1]

    if latest["adx"] < 20: return {"error": "Рынок слабый (ADX < 20)"}
    if latest["rsi"] > 70 or latest["rsi"] < 30: return {"error": "Рынок перегрет (RSI)"}
    if is_doji(m15["values"][0]): return {"error": "Формация Doji — сигнал пропущен"}

    trend = "up" if latest["close"] > latest["ema"] else "down"
    signal = "Buy" if trend == "up" else "Sell"
    price = latest["close"]
    atr = latest["atr"]
    tp_pct = round(atr / price * 100 * 2, 2)
    sl_pct = round(atr / price * 100, 2)
    confidence = 80 + (5 if trend == "up" else 0)
    return {"signal": signal, "price": price, "tp_pct": tp_pct, "sl_pct": sl_pct, "confidence": confidence}

def calc_levels(price, tp_pct, sl_pct, direction, spread=0.01, commission=0.02):
    adjust = (spread + commission) / 100
    if direction == "Buy":
        tp = round(price * (1 + tp_pct/100 - adjust), 4)
        sl = round(price * (1 - sl_pct/100 - adjust), 4)
    else:
        tp = round(price * (1 - tp_pct/100 + adjust), 4)
        sl = round(price * (1 + sl_pct/100 + adjust), 4)
    return tp, sl

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    uid = msg.from_user.id
    user_settings[uid] = {"asset": symbols[0], "mute": False, "strategy": strategies[0], "schedule": []}
    await msg.answer("Пора выбраться из матрицы", reply_markup=get_main_keyboard())

@dp.message()
async def handle(msg: types.Message):
    uid = msg.from_user.id
    text = msg.text
    if uid not in user_settings:
        await cmd_start(msg)
        return
    st = user_settings[uid]

    if text == "🔄 Получить сигнал":
        m15 = await fetch_data(st["asset"], "15min")
        h1 = await fetch_data(st["asset"], "1h")
        res = analyze_combined(m15, h1)
        if "error" in res:
            return await msg.answer(f"⚠️ {res['error']}")
        tp, sl = calc_levels(res["price"], res["tp_pct"], res["sl_pct"], res["signal"])
        return await msg.answer(
            f"📈 Сигнал по {st['asset']}:\n"
            f"📍 {res['signal']}\n"
            f"💰 Вход: {res['price']}\n"
            f"🎯 TP +{res['tp_pct']}% → {tp}\n"
            f"🛑 SL -{res['sl_pct']}% → {sl}\n"
            f"📊 Точность: {res['confidence']}%"
        )

    if text in [s.replace("/", "") for s in symbols]:
        st["asset"] = f"{text[:3]}/{text[3:]}"
        return await msg.answer(f"✅ Актив: {st['asset']}")

    if text == "🔕 Mute":
        st["mute"] = True
        return await msg.answer("🔕 Уведомления отключены")
    if text == "🔔 Unmute":
        st["mute"] = False
        return await msg.answer("🔔 Уведомления включены")

    if text == "🎯 Стратегия":
        st["strategy"] = strategies[0]
        return await msg.answer(f"🎯 Стратегия: {st['strategy']}")

    if text == "📊 Статус":
        mute = "🔕" if st["mute"] else "🔔"
        return await msg.answer(f"📊 Настройки:\nАктив: {st['asset']}\nСтратегия: {st['strategy']}\nMute: {mute}")

    if text == "🕒 Расписание":
        return await msg.answer("🕒 Расписание — скоро будет")

async def auto_signal_loop():
    while True:
        for uid, st in user_settings.items():
            if st["mute"]: continue
            m15 = await fetch_data(st["asset"], "15min")
            h1 = await fetch_data(st["asset"], "1h")
            res = analyze_combined(m15, h1)
            if "error" in res or res["confidence"] < 70: continue
            tp, sl = calc_levels(res["price"], res["tp_pct"], res["sl_pct"], res["signal"])
            await bot.send_message(uid,
                f"📢 Автосигнал по {st['asset']}:\n"
                f"📍 {res['signal']} @ {res['price']}\n"
                f"🎯 TP +{res['tp_pct']}% → {tp}\n"
                f"🛑 SL -{res['sl_pct']}% → {sl}\n"
                f"📊 Точность: {res['confidence']}%"
            )
        await asyncio.sleep(900)

async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
