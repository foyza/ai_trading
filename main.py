import asyncio
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import CommandStart
from datetime import datetime


BOT_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Хранение настроек по user_id
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

async def fetch_data(symbol):
    params = {"symbol": symbol, "interval": "15min", "outputsize": 100, "apikey": API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://api.twelvedata.com/time_series", params=params)
    return r.json()

def analyze(data, strategy):
    if "values" not in data:
        return {"error": data.get("message", "Ошибка данных")}
    price = float(data["values"][0]["close"])
    # Заглушка индикаторов:
    ma = "up" if strategy == strategies[0] else "down"
    rsi = ma
    macd = ma
    vote = sum([1 for x in (ma, rsi, macd) if x == ma])
    confidence = {3:100,2:80,1:60,0:50}[vote]
    signal = "Buy" if ma=="up" else "Sell"
    tp = 1.5 if strategy == strategies[0] else 2.0
    sl = 1.0 if strategy == strategies[0] else 1.2
    return {"signal": signal, "confidence": confidence, "tp_pct":tp, "sl_pct":sl, "price":price}

def calc_levels(price, tp_pct, sl_pct, direction):
    if direction == "Buy":
        tp = round(price*(1+tp_pct/100),4)
        sl = round(price*(1-sl_pct/100),4)
    else:
        tp = round(price*(1-tp_pct/100),4)
        sl = round(price*(1+sl_pct/100),4)
    return tp, sl

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    uid = msg.from_user.id
    user_settings[uid] = {"asset":symbols[0], "mute":False, "strategy":strategies[0], "schedule":[]}
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
        res = analyze(data, st["strategy"])
        if "error" in res:
            return await msg.answer(f"❌ {res['error']}")
        if res["confidence"] < 60:
            return await msg.answer(f"⚠️ Риск велик (точность: {res['confidence']}%)")
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
        choice = f"{text[:3]}/{text[3:]}"
        st["asset"] = choice
        return await msg.answer(f"✅ Актив: {choice}")

    if text == "🔕 Mute":
        st["mute"] = True
        return await msg.answer("🔕 Отключены уведомления")
    if text == "🔔 Unmute":
        st["mute"] = False
        return await msg.answer("🔔 Включены уведомления")

    if text == "🎯 Стратегия":
        st["strategy"] = strategies[1] if st["strategy"]==strategies[0] else strategies[0]
        return await msg.answer(f"🎯 Стратегия: {st['strategy']}")

    if text == "📊 Статус":
        mute = "🔕" if st["mute"] else "🔔"
        return await msg.answer(f"📊 Настройки:\nАктив: {st['asset']}\nСтратегия: {st['strategy']}\nMute: {mute}")

    if text == "🕒 Расписание":
        return await msg.answer("🕒 Расписание — в разработке")

async def auto_signal_loop():
    while True:
        for uid, st in user_settings.items():
            if st["mute"]: continue
            data = await fetch_data(st["asset"])
            res = analyze(data, st["strategy"])
            if "error" in res or res["confidence"] <= 70: continue
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
