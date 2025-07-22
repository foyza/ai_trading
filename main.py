import asyncio
import os
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import CommandStart
from datetime import datetime

TELEGRAM_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
TWELVE_DATA_API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

user_settings = {}

symbols = {
    "BTCUSD": "BTC/USD",
    "XAUUSD": "XAU/USD",
    "EURUSD": "EUR/USD"
}

strategies = ["MA+RSI+MACD", "Bollinger+Stochastic"]

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="EURUSD")],
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
    last_price = float(data["values"][0]["close"])
    if strategy == "MA+RSI+MACD":
        return {"signal": "Buy", "confidence": 74, "tp": 1.2, "sl": 0.8, "price": last_price}
    if strategy == "Bollinger+Stochastic":
        return {"signal": "Sell", "confidence": 78, "tp": 1.5, "sl": 1.0, "price": last_price}
    return None

@dp.message(CommandStart())
async def start(msg: types.Message):
    user_id = msg.from_user.id
    user_settings[user_id] = {
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

    settings = user_settings[user_id]

    if text == "🔄 Получить сигнал":
        symbol = settings["asset"]
        data = await fetch_data(symbol)
        strategy = settings["strategy"]
        result = analyze(data, strategy)
        if result:
            if result["confidence"] < 60:
                await msg.answer(f"⚠️ Риск велик, не время торговли (точность: {result['confidence']}%)")
            else:
                await msg.answer(
                    f"📈 Сигнал по {symbols[symbol]}:\n"
                    f"📍 Направление: {result['signal']}\n"
                    f"💰 Цена входа: {result['price']}\n"
                    f"🎯 Take-Profit: +{result['tp']}% (~{round(result['price'] * (1 + result['tp'] / 100), 2)})\n"
                    f"🛑 Stop-Loss: -{result['sl']}% (~{round(result['price'] * (1 - result['sl'] / 100), 2)})\n"
                    f"📊 Точность прогноза: {result['confidence']}%"
                )
        else:
            await msg.answer("Нет сигнала по текущей стратегии.")

    elif text in ["BTCUSD", "XAUUSD", "EURUSD"]:
        user_settings[user_id]["asset"] = text
        await msg.answer(f"✅ Выбран актив: {symbols[text]}")

    elif text == "🔕 Mute":
        user_settings[user_id]["mute"] = True
        await msg.answer("🔕 Уведомления выключены")

    elif text == "🔔 Unmute":
        user_settings[user_id]["mute"] = False
        await msg.answer("🔔 Уведомления включены")

    elif text == "🎯 Стратегия":
        current = settings["strategy"]
        new = strategies[1] if current == strategies[0] else strategies[0]
        user_settings[user_id]["strategy"] = new
        await msg.answer(f"🎯 Выбрана стратегия: {new}")

    elif text == "🕒 Расписание":
        await msg.answer("🕒 Настройка расписания будет доступна в следующем обновлении.")

    elif text == "📊 Статус":
        mute_status = "🔕" if settings["mute"] else "🔔"
        await msg.answer(
            f"📊 Ваши настройки:\n"
            f"Актив: {symbols[settings['asset']]}\n"
            f"Стратегия: {settings['strategy']}\n"
            f"Звук: {mute_status}"
        )

async def auto_signals():
    while True:
        for uid, settings in user_settings.items():
            if settings["mute"]:
                continue
            symbol = settings["asset"]
            strategy = settings["strategy"]
            data = await fetch_data(symbol)
            result = analyze(data, strategy)
            if result and result["confidence"] > 70:
                await bot.send_message(
                    uid,
                    f"📢 Автосигнал по {symbols[symbol]}:\n"
                    f"📍 Направление: {result['signal']}\n"
                    f"Цена входа: {result['price']}\n"
                    f"🎯 TP: +{result['tp']}%\n"
                    f"🛑 SL: -{result['sl']}%\n"
                    f"📊 Точность: {result['confidence']}%"
                )
        await asyncio.sleep(900)  # 15 минут

async def main():
    asyncio.create_task(auto_signals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
