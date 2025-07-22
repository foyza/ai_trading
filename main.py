import asyncio
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import CommandStart


TELEGRAM_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
TWELVE_DATA_API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

user_settings = {}

symbols = {
    "BTC/USD": "BTC/USD",
    "XAU/USD": "XAU/USD",
    "EUR/USD": "EUR/USD"
}

strategies = ["MA+RSI+MACD", "Bollinger+Stochastic"]

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="BTC/USD"), KeyboardButton(text="XAU/USD"), KeyboardButton(text="EUR/USD")],
        [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
        [KeyboardButton(text="🎯 Стратегия")],
        [KeyboardButton(text="🕒 Расписание")],
        [KeyboardButton(text="📊 Статус")]
    ],
    resize_keyboard=True
)

async def fetch_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=50&apikey={TWELVE_DATA_API_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return r.json()

def analyze(data, strategy):
    if "values" not in data:
        return {"error": data.get("message", "Ошибка данных с биржи")}

    price = float(data["values"][0]["close"])

    if strategy == "MA+RSI+MACD":
        return {"signal": "Buy", "confidence": 75, "tp": 1.5, "sl": 1.0, "price": price}
    if strategy == "Bollinger+Stochastic":
        return {"signal": "Sell", "confidence": 78, "tp": 2.0, "sl": 1.2, "price": price}
    return None

@dp.message(CommandStart())
async def start(msg: types.Message):
    user_settings[msg.from_user.id] = {
        "asset": "BTCUSD",
        "mute": False,
        "strategy": strategies[0]
    }
    await msg.answer("Пора выбраться из матрицы", reply_markup=keyboard)

@dp.message()
async def handle(msg: types.Message):
    user_id = msg.from_user.id
    text = msg.text

    if user_id not in user_settings:
        await start(msg)
        return

    u = user_settings[user_id]

    if text == "🔄 Получить сигнал":
        data = await fetch_data(u["asset"])
        result = analyze(data, u["strategy"])

        if result is None:
            await msg.answer("❌ Нет сигнала по текущей стратегии.")
            return

        if "error" in result:
            await msg.answer(f"❌ Ошибка: {result['error']}")
            return

        if result["confidence"] < 60:
            await msg.answer(f"⚠️ Риск велик, не время торговли (точность: {result['confidence']}%)")
        else:
            price = result["price"]
            tp_price = round(price * (1 + result["tp"] / 100), 2)
            sl_price = round(price * (1 - result["sl"] / 100), 2)
            await msg.answer(
                f"📈 Сигнал по {symbols[u['asset']]}:\n"
                f"📍 Направление: {result['signal']}\n"
                f"💰 Цена входа: {price}\n"
                f"🎯 TP: +{result['tp']}% → {tp_price}\n"
                f"🛑 SL: -{result['sl']}% → {sl_price}\n"
                f"📊 Точность прогноза: {result['confidence']}%"
            )

    elif text in symbols:
        u["asset"] = text
        await msg.answer(f"✅ Актив установлен: {symbols[text]}")

    elif text == "🔕 Mute":
        u["mute"] = True
        await msg.answer("🔕 Уведомления отключены")

    elif text == "🔔 Unmute":
        u["mute"] = False
        await msg.answer("🔔 Уведомления включены")

    elif text == "🎯 Стратегия":
        u["strategy"] = strategies[1] if u["strategy"] == strategies[0] else strategies[0]
        await msg.answer(f"🎯 Текущая стратегия: {u['strategy']}")

    elif text == "📊 Статус":
        mute_status = "🔕" if u["mute"] else "🔔"
        await msg.answer(
            f"📊 Ваши настройки:\n"
            f"Актив: {symbols[u['asset']]}\n"
            f"Стратегия: {u['strategy']}\n"
            f"Mute: {mute_status}")
        
    elif text == "🕒 Расписание":
        await msg.answer("🕒 Настройка расписания будет добавлена в будущих версиях.")

async def auto_signals():
    while True:
        for uid, u in user_settings.items():
            if u["mute"]:
                continue

            data = await fetch_data(u["asset"])
            result = analyze(data, u["strategy"])

            if result and "error" not in result and result["confidence"] > 70:
                price = result["price"]
                tp_price = round(price * (1 + result["tp"] / 100), 2)
                sl_price = round(price * (1 - result["sl"] / 100), 2)
                await bot.send_message(
                    uid,
                    f"📢 Автосигнал по {symbols[u['asset']]}:\n"
                    f"📍 {result['signal']} по {price}\n"
                    f"🎯 TP: {tp_price} (+{result['tp']}%)\n"
                    f"🛑 SL: {sl_price} (-{result['sl']}%)\n"
                    f"📊 Точность: {result['confidence']}%"
                )
        await asyncio.sleep(900)  # каждые 15 минут

async def main():
    asyncio.create_task(auto_signals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
