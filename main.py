import asyncio
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import CommandStart
from datetime import datetime, timedelta

# Загрузка переменных

BOT_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Хранение настроек пользователя
user_settings = {}

symbols = ["BTC/USD", "XAU/USD", "EUR/USD"]
strategies = ["MA+RSI+MACD", "Bollinger+Stochastic"]

def get_main_keyboard():
    buttons = [
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text=s.split("/")[0] + "USD") for s in symbols],
        [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
        [KeyboardButton(text="🎯 Стратегия")],
        [KeyboardButton(text="🕒 Расписание")],
        [KeyboardButton(text="📊 Статус")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def fetch_data(symbol):
    params = {
        "symbol": symbol,
        "interval": "15min",
        "outputsize": 100,
        "apikey": API_KEY
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("https://api.twelvedata.com/time_series", params=params)
    return resp.json()

def analyze(data, strategy):
    if "values" not in data:
        return {"error": data.get("message", "Нет данных")}
    price = float(data["values"][0]["close"])
    # Тестовые сигналы — заменить на реальную логику
    if strategy == "MA+RSI+MACD":
        return {"signal": "Buy", "confidence": 80, "tp_pct": 1.5, "sl_pct": 1.0, "price": price}
    else:
        return {"signal": "Sell", "confidence": 82, "tp_pct": 2.0, "sl_pct": 1.2, "price": price}

def calc_levels(price, tp_pct, sl_pct, direction):
    if direction == "Buy":
        tp_price = round(price * (1 + tp_pct / 100), 4)
        sl_price = round(price * (1 - sl_pct / 100), 4)
    else:
        tp_price = round(price * (1 - tp_pct / 100), 4)
        sl_price = round(price * (1 + sl_pct / 100), 4)
    return tp_price, sl_price

@dp.message(CommandStart())
async def start(msg: types.Message):
    user_id = msg.from_user.id
    user_settings[user_id] = {
        "asset": symbols[0],
        "mute": False,
        "strategy": strategies[0],
        "schedule": {}  # future: хранение расписания
    }
    await msg.answer("Пора выбраться из матрицы", reply_markup=get_main_keyboard())

@dp.message()
async def handle(msg: types.Message):
    uid = msg.from_user.id
    text = msg.text
    if uid not in user_settings:
        await start(msg)
        return

    st = user_settings[uid]

    if text == "🔄 Получить сигнал":
        data = await fetch_data(st["asset"])
        res = analyze(data, st["strategy"])
        if "error" in res:
            return await msg.answer(f"❌ {res['error']}")
        if res["confidence"] < 60:
            return await msg.answer(f"⚠️ Риск велик, не время торговли (точность: {res['confidence']}%)")
        tp, sl = calc_levels(res["price"], res["tp_pct"], res["sl_pct"], res["signal"])
        return await msg.answer(
            f"📈 Сигнал по {st['asset']}:\n"
            f"📍 Направление: {res['signal']}\n"
            f"💰 Входная цена: {res['price']}\n"
            f"🎯 TP: +{res['tp_pct']}% → {tp}\n"
            f"🛑 SL: -{res['sl_pct']}% → {sl}\n"
            f"📊 Точность: {res['confidence']}%"
        )

    if text in ["BTCUSD", "XAUUSD", "EURUSD"]:
        choice = text.replace("USD","") + "/USD"
        if choice in symbols:
            st["asset"] = choice
            return await msg.answer(f"✅ Актив: {choice}")

    if text == "🔕 Mute":
        st["mute"] = True
        return await msg.answer("🔕 Уведомления отключены")
    if text == "🔔 Unmute":
        st["mute"] = False
        return await msg.answer("🔔 Уведомления включены")

    if text == "🎯 Стратегия":
        st["strategy"] = strategies[1] if st["strategy"] == strategies[0] else strategies[0]
        return await msg.answer(f"🎯 Стратегия: {st['strategy']}")
        
    if text == "📊 Статус":
        mute = "🔕" if st["mute"] else "🔔"
        return await msg.answer(
            f"📊 Ваши настройки:\n"
            f"Актив: {st['asset']}\n"
            f"Стратегия: {st['strategy']}\n"
            f"Mute: {mute}"
        )

    if text == "🕒 Расписание":
        return await msg.answer("🕒 Расписание пока не реализовано")

async def auto_send():
    while True:
        for uid, st in list(user_settings.items()):
            if st["mute"]: continue
            data = await fetch_data(st["asset"])
            res = analyze(data, st["strategy"])
            if "error" in res or res["confidence"] <= 70: continue
            tp, sl = calc_levels(res["price"], res["tp_pct"], res["sl_pct"], res["signal"])
            try:
                await bot.send_message(
                    uid,
                    f"📢 Авто-сигнал по {st['asset']}:\n"
                    f"📍 {res['signal']} @ {res['price']}\n"
                    f"🎯 TP: {tp} (+{res['tp_pct']}%)\n"
                    f"🛑 SL: {sl} (-{res['sl_pct']}%)\n"
                    f"📊 Точность: {res['confidence']}%"
                )
            except:
                pass
        await asyncio.sleep(900)

async def main():
    asyncio.create_task(auto_send())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
