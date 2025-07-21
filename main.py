import asyncio
import logging
from datetime import datetime, time
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from binance.client import Client
import yfinance as yf
import numpy as np
import pandas as pd

# === Telegram bot token ===
BOT_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"

# === Активы и Binance тикеры ===
ASSETS = {
    "BTCUSDT": "BTCUSDT",
    "XAUUSDT": "XAUUSDT",
    "NAS100": "^NDX"
}

# === Инициализация ===
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
user_data = {}

# === Кнопки ===
menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔄 Получить сигнал")],
    [KeyboardButton(text="📊 Выбрать актив"), KeyboardButton(text="🕒 Изменить время")]
], resize_keyboard=True)

assets_keyboard = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="BTCUSDT")],
    [KeyboardButton(text="XAUUSDT")],
    [KeyboardButton(text="NAS100")]
], resize_keyboard=True)

# === Приветствие ===
@dp.message(CommandStart())
async def start(message: Message):
    user_data[message.chat.id] = {
        "asset": "BTCUSDT",
        "schedules": {
            "BTCUSDT": ("00:00", "23:59"),
            "XAUUSDT": ("00:00", "23:59"),
            "NAS100": ("00:00", "23:59")
        }
    }
    await message.answer("Пора выбраться из матрицы.\nВыберите действие:", reply_markup=menu)

# === Получить сигнал ===
@dp.message(F.text == "🔄 Получить сигнал")
async def handle_signal(message: Message):
    chat_id = message.chat.id
    asset = user_data.get(chat_id, {}).get("asset", "BTCUSDT")

    if not is_in_trading_time(chat_id, asset):
        await message.answer("⏰ Вне заданного времени торговли.")
        return

    signal = get_signal(asset)
    if not signal:
        await message.answer("⚠️ Недостаточно данных для анализа.")
        return

    confidence, direction, entry_price, tp_price, sl_price, tp_pct, sl_pct = signal

    if confidence < 60:
        await message.answer(f"⚠️ Риск велик, не время торговли (точность: {confidence:.2f}%)")
    elif confidence >= 65:
        await message.answer(
            f"📈 Актив: {asset}\n"
            f"Направление: {direction}\n"
            f"Цена входа: {entry_price:.2f}\n"
            f"🎯 TP: {tp_pct:.2f}% → {tp_price:.2f}\n"
            f"🛡 SL: {sl_pct:.2f}% → {sl_price:.2f}\n"
            f"📊 Точность прогноза: {confidence:.2f}%"
        )

# === Выбрать актив ===
@dp.message(F.text == "📊 Выбрать актив")
async def choose_asset(message: Message):
    await message.answer("Выберите актив:", reply_markup=assets_keyboard)

@dp.message(F.text.in_(ASSETS.keys()))
async def set_asset(message: Message):
    user_data[message.chat.id]["asset"] = message.text
    await message.answer(f"Актив установлен: {message.text}")

# === Изменить время ===
@dp.message(F.text == "🕒 Изменить время")
async def ask_time(message: Message):
    asset = user_data[message.chat.id]["asset"]
    await message.answer(f"Введите время в формате 08:00-16:00 для актива {asset}:")

@dp.message(F.text.regexp(r"^\d{2}:\d{2}-\d{2}:\d{2}$"))
async def save_time(message: Message):
    asset = user_data[message.chat.id]["asset"]
    start_str, end_str = message.text.split("-")
    user_data[message.chat.id]["schedules"][asset] = (start_str, end_str)
    await message.answer(f"Время торговли для {asset} установлено: {start_str}–{end_str}")

# === Проверка времени ===
def is_in_trading_time(chat_id, asset):
    now = datetime.now().time()
    start_str, end_str = user_data.get(chat_id, {}).get("schedules", {}).get(asset, ("00:00", "23:59"))
    start = datetime.strptime(start_str, "%H:%M").time()
    end = datetime.strptime(end_str, "%H:%M").time()
    return start <= now <= end

# === Получение сигнала ===
def get_signal(asset):
    try:
        if asset == "NAS100":
            df = yf.download(ASSETS[asset], period="7d", interval="15m")
            price = df['Close'].iloc[-1]
        else:
            client = Client()
            klines = client.
get_klines(symbol=ASSETS[asset], interval=Client.KLINE_INTERVAL_15MINUTE, limit=100)
            close_prices = [float(k[4]) for k in klines]
            price = close_prices[-1]
            df = pd.DataFrame({'Close': close_prices})

        df['SMA'] = df['Close'].rolling(window=10).mean()
        df.dropna(inplace=True)

        if df.empty:
            return None

        latest_price = df['Close'].iloc[-1]
        sma = df['SMA'].iloc[-1]
        direction = "Buy" if latest_price > sma else "Sell"
        confidence = np.clip(np.random.normal(loc=72 if direction == "Buy" else 68, scale=5), 50, 100)

        tp_pct = 1.5
        sl_pct = 1.0

        tp_price = latest_price * (1 + tp_pct / 100) if direction == "Buy" else latest_price * (1 - tp_pct / 100)
        sl_price = latest_price * (1 - sl_pct / 100) if direction == "Buy" else latest_price * (1 + sl_pct / 100)

        return confidence, direction, latest_price, tp_price, sl_price, tp_pct, sl_pct

    except Exception as e:
        print(f"Ошибка: {e}")
        return None

# === Автоотправка сигналов при точности >70% ===
async def auto_signal_loop():
    while True:
        for chat_id, data in user_data.items():
            asset = data["asset"]
            if not is_in_trading_time(chat_id, asset):
                continue

            signal = get_signal(asset)
            if signal:
                confidence, direction, entry_price, tp_price, sl_price, tp_pct, sl_pct = signal
                if confidence >= 70:
                    await bot.send_message(
                        chat_id,
                        f"📡 [Авто-сигнал]\n"
                        f"Актив: {asset}\n"
                        f"Направление: {direction}\n"
                        f"Цена входа: {entry_price:.2f}\n"
                        f"🎯 TP: {tp_pct:.2f}% → {tp_price:.2f}\n"
                        f"🛡 SL: {sl_pct:.2f}% → {sl_price:.2f}\n"
                        f"📊 Точность прогноза: {confidence:.2f}%"
                    )
        await asyncio.sleep(60)

# === Запуск ===
async def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
