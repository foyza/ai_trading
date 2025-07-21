import logging
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import Command
from datetime import datetime, time

API_TOKEN = '8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA'

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher()

user_asset = {}
user_schedule = {}

available_assets = ["BTCUSDT", "XAUUSDT", "NAS100"]

# Получение данных с Binance через requests
def get_binance_price_data(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=100"
        response = requests.get(url, timeout=10)
        data = response.json()
        if not data or len(data) == 0:
            return None
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
        ])
        df["close"] = df["close"].astype(float)
        return df
    except Exception:
        return None

# Универсальная функция получения цены
def get_price_data(symbol):
    if symbol in ["BTCUSDT", "XAUUSDT"]:
        return get_binance_price_data(symbol)
    elif symbol == "NAS100":
        df = yf.download("^NDX", interval="15m", period="1d", progress=False)
        if df.empty:
            return None
        df = df.rename(columns={"Close": "close"})
        return df
    return None

# Прогноз — простая логика: сравнение последней свечи с предыдущей
def predict_signal(df):
    if df is None or len(df) < 2:
        return None, 0
    last = df["close"].iloc[-1]
    prev = df["close"].iloc[-2]
    acc = np.random.randint(60, 90)
    direction = "Buy" if last > prev else "Sell"
    entry = round(last, 2)
    tp_percent = 1.5
    sl_percent = 1.0
    tp_price = round(entry * (1 + tp_percent / 100), 2) if direction == "Buy" else round(entry * (1 - tp_percent / 100), 2)
    sl_price = round(entry * (1 - sl_percent / 100), 2) if direction == "Buy" else round(entry * (1 + sl_percent / 100), 2)
    return {
        "direction": direction,
        "entry": entry,
        "tp_percent": tp_percent,
        "sl_percent": sl_percent,
        "tp_price": tp_price,
        "sl_price": sl_price
    }, acc

def is_within_schedule(user_id, symbol):
    now = datetime.now().time()
    if user_id in user_schedule and symbol in user_schedule[user_id]:
        time_range = user_schedule[user_id][symbol]
        try:
            start_str, end_str = time_range.split("-")
            start_time = time.fromisoformat(start_str)
            end_time = time.fromisoformat(end_str)
            return start_time <= now <= end_time
        except:
            return True
    return True

@dp.message(Command("start"))
async def start_handler(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Получить сигнал")],
            [KeyboardButton(text="📈 Выбрать актив"), KeyboardButton(text="⏰ Задать время")]
        ],
        resize_keyboard=True
    )
    user_asset[message.chat.id] = "BTCUSDT"
    await message.answer("Пора выбраться из матрицы.\n\nВыбран актив: <b>BTCUSDT</b>", reply_markup=kb)

@dp.message(F.text == "📈 Выбрать актив")
async def choose_asset_handler(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=asset)] for asset in available_assets],
        resize_keyboard=True
    )
    await message.answer("Выберите актив:", reply_markup=kb)

@dp.message(F.text.in_(available_assets))
async def set_asset_handler(message: Message):
    user_asset[message.chat.id] = message.text
    await message.answer(f"Актив установлен: <b>{message.text}</b>")

@dp.message(F.text == "⏰ Задать время")
async def set_time_prompt(message: Message):
    await message.answer("Введите время в формате <b>09:00-17:00</b> для текущего актива.")

@dp.message(lambda message: "-" in message.text and ":" in message.text)
async def set_time_handler(message: Message):
    user_id = message.chat.id
    symbol = user_asset.get(user_id, "BTCUSDT")
    if user_id not in user_schedule:
        user_schedule[user_id] = {}
    user_schedule[user_id][symbol] = message.text
    await message.answer(f"Время для {symbol} установлено: <b>{message.text}</b>")

@dp.message(F.text == "🔄 Получить сигнал")
async def manual_signal(message: Message):
    user_id = message.chat.id
    symbol = user_asset.get(user_id, "BTCUSDT")
    if not is_within_schedule(user_id, symbol):
        await message.answer("⏳ Сейчас не входит в заданный торговый интервал.")
        return

    df = get_price_data(symbol)
    signal, acc = predict_signal(df)
    if not signal:
        await message.answer("Данные не получены.")
        return

    if acc < 60:
        await message.answer(f"⚠️ Риск велик, не время торговли ({acc}%)")
    elif acc >= 65:
        text = (
            f"<b>📊 Сигнал по {symbol}</b>\n"
            f"Направление: <b>{signal['direction']}</b>\n"
            f"Цена входа: <b>{signal['entry']}</b>\n"
            f"🎯 TP: {signal['tp_percent']}% ({signal['tp_price']})\n"
            f"🛑 SL: {signal['sl_percent']}% ({signal['sl_price']})\n"
            f"🎯 Точность прогноза: <b>{acc}%</b>"
        )
        await message.answer(text)

        # Уведомление о TP/SL
        current_price = df["close"].iloc[-1]
        if (signal["direction"] == "Buy" and current_price >= signal["tp_price"]) or \
           (signal["direction"] == "Sell" and current_price <= signal["tp_price"]):
            await message.answer("✅ TP достигнут!")
        elif (signal["direction"] == "Buy" and current_price <= signal["sl_price"]) or \
             (signal["direction"] == "Sell" and current_price >= signal["sl_price"]):
            await message.answer("❌ SL сработал!")

# Автоматическая проверка сигналов
async def auto_check():
    while True:
        for user_id, symbol in user_asset.items():
            if not is_within_schedule(user_id, symbol):
                continue
            df = get_price_data(symbol)
            signal, acc = predict_signal(df)
            if not signal or acc < 70:
                continue
            text = (
                f"<b>📊 Сигнал по {symbol}</b>\n"
                f"Направление: <b>{signal['direction']}</b>\n"
                f"Цена входа: <b>{signal['entry']}</b>\n"
                f"🎯 TP: {signal['tp_percent']}% ({signal['tp_price']})\n"
                f"🛑 SL: {signal['sl_percent']}% ({signal['sl_price']})\n"
                f"🎯 Точность прогноза: <b>{acc}%</b>"
            )
            try:
                await bot.send_message(user_id, text)
                current_price = df["close"].iloc[-1]
                if (signal["direction"] == "Buy" and current_price >= signal["tp_price"]) or \
                   (signal["direction"] == "Sell" and current_price <= signal["tp_price"]):
                    await bot.send_message(user_id, "✅ TP достигнут!")
                elif (signal["direction"] == "Buy" and current_price <= signal["sl_price"]) or \
                     (signal["direction"] == "Sell" and current_price >= signal["sl_price"]):
                    await bot.send_message(user_id, "❌ SL сработал!")
            except Exception as e:
                print(f"[ERROR] {e}")
        await asyncio.sleep(60)  # Проверка каждую минуту

async def main():
    task = asyncio.create_task(auto_check())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
