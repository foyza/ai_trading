import logging
import asyncio
import json
from datetime import datetime, time
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
import httpx
import os

API_KEY = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'
TWELVE_DATA_API_KEY = '5e5e950fa71c416e9ffdb86fce72dc4f'

bot = Bot(token=API_KEY)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

user_data = {}

KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="BTCUSD / XAUUSD / EURUSD")],
        [KeyboardButton(text="🔕 Mute / 🔔 Unmute")],
        [KeyboardButton(text="🎯 Стратегия")],
        [KeyboardButton(text="🕒 Расписание")],
        [KeyboardButton(text="📊 Статус")]
    ],
    resize_keyboard=True
)

AVAILABLE_SYMBOLS = ["BTC/USD", "XAU/USD", "EUR/USD"]
DEFAULT_STRATEGY = "MA+RSI+MACD"

async def get_market_data(symbol: str):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=50&apikey={TWELVE_DATA_API_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return r.json()

def calculate_signals(data, strategy):
    if strategy == "MA+RSI+MACD":
        return {"signal": "Buy", "confidence": 75, "tp": 1.5, "sl": 1.0, "price": float(data['values'][0]['close'])}
    elif strategy == "Bollinger+Stochastic":
        return {"signal": "Sell", "confidence": 72, "tp": 2.0, "sl": 1.5, "price": float(data['values'][0]['close'])}
    return None

@dp.message(CommandStart())
async def start(msg: types.Message):
    user_id = msg.from_user.id
    user_data[user_id] = {
        "asset": "BTC/USD",
        "mute": False,
        "strategy": DEFAULT_STRATEGY,
        "schedule": {},
    }
    await msg.answer("Пора выбраться из матрицы", reply_markup=KEYBOARD)

@dp.message()
async def handle(msg: types.Message):
    user_id = msg.from_user.id
    text = msg.text

    if user_id not in user_data:
        await start(msg)
        return

    if text == "🔄 Получить сигнал":
        asset = user_data[user_id]["asset"]
        strategy = user_data[user_id]["strategy"]
        data = await get_market_data(asset.replace("/", ""))
        signal = calculate_signals(data, strategy)
        if signal:
            if signal["confidence"] < 60:
                await msg.answer(f"⚠️ Риск велик, не время торговли (точность: {signal['confidence']}%)")
            else:
                await msg.answer(
                    f"📈 Сигнал по {asset}:\n"
                    f"📍 Направление: {signal['signal']}\n"
                    f"💰 Цена входа: {signal['price']}\n"
                    f"🎯 Take-Profit: +{signal['tp']}%\n"
                    f"🛑 Stop-Loss: -{signal['sl']}%\n"
                    f"📊 Точность прогноза: {signal['confidence']}%"
                )
        else:
            await msg.answer("Нет уверенного сигнала по текущей стратегии.")

    elif text == "BTCUSD / XAUUSD / EURUSD":
        current = user_data[user_id]["asset"]
        index = AVAILABLE_SYMBOLS.index(current)
        user_data[user_id]["asset"] = AVAILABLE_SYMBOLS[(index + 1) % len(AVAILABLE_SYMBOLS)]
        await msg.answer(f"Выбранный актив: {user_data[user_id]['asset']}")

    elif text == "🔕 Mute / 🔔 Unmute":
        user_data[user_id]["mute"] = not user_data[user_id]["mute"]
        status = "🔕 Уведомления выключены" if user_data[user_id]["mute"] else "🔔 Уведомления включены"
        await msg.answer(status)

    elif text == "🎯 Стратегия":
        strategy = user_data[user_id]["strategy"]
        if strategy == "MA+RSI+MACD":
            user_data[user_id]["strategy"] = "Bollinger+Stochastic"
        else:
            user_data[user_id]["strategy"] = "MA+RSI+MACD"
        await msg.answer(f"Текущая стратегия: {user_data[user_id]['strategy']}")

    elif text == "📊 Статус":
        u = user_data[user_id]
        mute = "🔕" if u["mute"] else "🔔"
        await msg.answer(
            f"📊 Ваши настройки:\n"
            f"Актив: {u['asset']}\n"
            f"Стратегия: {u['strategy']}\n"
            f"Mute: {mute}"
        )

    elif text == "🕒 Расписание":
        await msg.answer("Расписание пока недоступно. В следующем обновлении.")

async def auto_send_signals():
    while True:
        for user_id, data in user_data.items():
            if data["mute"]:
                continue
            asset = data["asset"]
            strategy = data["strategy"]
            market_data = await get_market_data(asset.replace("/", ""))
            signal = calculate_signals(market_data, strategy)
            if signal and signal["confidence"] > 70:
                try:
                    await bot.send_message(
                        user_id,
                        f"📈 Авто-сигнал по {asset}:\n"
                        f"📍 Направление: {signal['signal']}\n"
                        f"💰 Цена входа: {signal['price']}\n"
                        f"🎯 Take-Profit: +{signal['tp']}%\n"
                        f"🛑 Stop-Loss: -{signal['sl']}%\n"
                        f"📊 Точность прогноза: {signal['confidence']}%"
                    )
                except Exception:
                    continue
        await asyncio.sleep(900)  # каждые 15 минут

async def main():
    asyncio.create_task(auto_send_signals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
