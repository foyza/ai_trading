import asyncio
import httpx
import numpy as np
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
strategies = ["Scalping"]

def get_main_keyboard():
    buttons = [
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text=s.replace("/", "")) for s in symbols],
        [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
        [KeyboardButton(text="🎯 Стратегия")],
        [KeyboardButton(text="🕒 Расписание")],
        [KeyboardButton(text="📊 Статус")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

async def fetch_data(symbol):
    params = {
        "symbol": symbol,
        "interval": "15min",
        "outputsize": 100,
        "apikey": API_KEY
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://api.twelvedata.com/time_series", params=params)
    return r.json()

def rsi(values, period=14):
    deltas = np.diff(values)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down else 0
    rsi_series = [100 - 100 / (1 + rs)]
    for delta in deltas[period:]:
        upval = max(delta, 0)
        downval = -min(delta, 0)
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down else 0
        rsi_series.append(100 - 100 / (1 + rs))
    return rsi_series[-1]

def macd(values):
    ema12 = np.convolve(values, np.ones(12)/12, mode='valid')
    ema26 = np.convolve(values, np.ones(26)/26, mode='valid')
    macd_line = ema12[-1] - ema26[-1]
    return macd_line

def bollinger(values, period=20):
    sma = np.mean(values[-period:])
    std = np.std(values[-period:])
    upper = sma + 2 * std
    lower = sma - 2 * std
    return upper, lower

def trend_direction(values):
    if values[-1] > values[-5]:
        return "up"
    elif values[-1] < values[-5]:
        return "down"
    return "sideways"

def candlestick_pattern(data):
    recent = data[-1]
    open_, close = float(recent["open"]), float(recent["close"])
    high, low = float(recent["high"]), float(recent["low"])
    body = abs(close - open_)
    shadow = high - low
    if body < shadow * 0.3:
        return "Doji"
    elif close > open_:
        return "Bullish"
    else:
        return "Bearish"

def analyze(data):
    if "values" not in data:
        return {"error": data.get("message", "Ошибка данных")}
    
    candles = data["values"]
    closes = np.array([float(c["close"]) for c in candles])[::-1]
    price = closes[-1]

    rsi_val = rsi(closes)
    macd_val = macd(closes)
    bb_upper, bb_lower = bollinger(closes)
    trend = trend_direction(closes)
    candle_pat = candlestick_pattern(candles[::-1])

    votes = 0
    if trend == "up": votes += 1
    if macd_val > 0: votes += 1
    if rsi_val < 70: votes += 1
    if candle_pat == "Bullish": votes += 1

    if votes >= 3:
        signal = "Buy"
    elif votes <= 1:
        signal = "Sell"
    else:
        signal = "Hold"

    confidence = round(votes * 25)
    tp_pct = 0.8 + (votes * 0.2)
    sl_pct = 0.6

    return {
        "signal": signal,
        "confidence": confidence,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "price": price
    }

def calc_levels(price, tp_pct, sl_pct, direction):
    if direction == "Buy":
        tp = round(price * (1 + tp_pct / 100), 4)
        sl = round(price * (1 - sl_pct / 100), 4)
    else:
        tp = round(price * (1 - tp_pct / 100), 4)
        sl = round(price * (1 + sl_pct / 100), 4)
    return tp, sl

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    uid = msg.from_user.iduser_settings[uid] = {"asset": symbols[0], "mute": False, "strategy": strategies[0], "schedule": []}
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
        data = await fetch_data(st["asset"])
        res = analyze(data)
        if "error" in res:
            return await msg.answer(f"❌ {res['error']}")
        if res["signal"] == "Hold":
            return await msg.answer("⏸️ Сигнал не ясен — тренд боковой.")
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
        return await msg.answer("🔕 Отключены уведомления")
    if text == "🔔 Unmute":
        st["mute"] = False
        return await msg.answer("🔔 Включены уведомления")
    if text == "🎯 Стратегия":
        return await msg.answer("📌 Стратегия: Scalping (фиксирована)")
    if text == "📊 Статус":
        mute = "🔕" if st["mute"] else "🔔"
        return await msg.answer(f"📊 Настройки:\nАктив: {st['asset']}\nMute: {mute}")
    if text == "🕒 Расписание":
        return await msg.answer("🕒 Расписание — в разработке")

async def auto_signal_loop():
    while True:
        for uid, st in user_settings.items():
            if st["mute"]: continue
            data = await fetch_data(st["asset"])
            res = analyze(data)
            if res.get("signal") in ["Buy", "Sell"] and res["confidence"] >= 70:
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
