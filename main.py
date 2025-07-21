import asyncio
import logging
from datetime import datetime, time as dtime

import numpy as np
import pandas as pd
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from binance import Client
from binance.helpers import round_step_size
import yfinance as yf

# === НАСТРОЙКИ ===
API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

ASSETS = ["BTCUSDT", "XAUUSDT", "NAS100"]
SCHEDULE = {symbol: ("00:00", "23:59") for symbol in ASSETS}
current_asset = {}

client = Client()

logging.basicConfig(level=logging.INFO)

# === КНОПКИ ===
keyboard = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔄 Получить сигнал")],
    [KeyboardButton(text="📈 Актив: BTCUSDT"), KeyboardButton(text="📈 Актив: XAUUSDT"), KeyboardButton(text="📈 Актив: NAS100")],
    [KeyboardButton(text="⏰ Время торговли (09:00-17:00)")]
], resize_keyboard=True)

# === МОДЕЛЬ ПРОГНОЗА (ЗАГЛУШКА) ===
def predict_signal(df: pd.DataFrame) -> dict:
    """Пример: простая логика тренда"""
    last_close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-2]
    direction = "Buy" if last_close > prev_close else "Sell"
    accuracy = np.random.randint(55, 95)

    tp_percent = 1.2
    sl_percent = 0.8

    tp_price = round(last_close * (1 + tp_percent / 100), 2) if direction == "Buy" else round(last_close * (1 - tp_percent / 100), 2)
    sl_price = round(last_close * (1 - sl_percent / 100), 2) if direction == "Buy" else round(last_close * (1 + sl_percent / 100), 2)

    return {
        "direction": direction,
        "entry": last_close,
        "tp_percent": tp_percent,
        "sl_percent": sl_percent,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "accuracy": accuracy
    }

# === ДАННЫЕ С BINANCE или YAHOO ===
def fetch_data(symbol):
    try:
        if symbol == "NAS100":
            data = yf.download("^NDX", period="5d", interval="15m")
            df = pd.DataFrame({
                "time": data.index,
                "open": data["Open"],
                "high": data["High"],
                "low": data["Low"],
                "close": data["Close"]
            })
        else:
            klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=50)
            df = pd.DataFrame(klines, columns=["time", "o", "h", "l", "c", "v", "ct", "qv", "nt", "tb", "qtb", "i"])
            df["time"] = pd.to_datetime(df["time"], unit="ms")
            df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"}, inplace=True)
            df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)
        return df
    except Exception as e:
        logging.warning(f"Ошибка получения данных: {e}")
        return None

# === ПРОВЕРКА ВРЕМЕНИ ===
def is_within_trading_hours(symbol):
    now = datetime.now().time()
    start_str, end_str = SCHEDULE[symbol]
    start = datetime.strptime(start_str, "%H:%M").time()
    end = datetime.strptime(end_str, "%H:%M").time()
    return start <= now <= end

# === СИГНАЛ ===
async def send_signal(user_id, symbol):
    if not is_within_trading_hours(symbol):
        return

    df = fetch_data(symbol)
    if df is None or len(df) < 20:
        await bot.send_message(user_id, f"⚠️ Недостаточно данных для {symbol}")
        return

    signal = predict_signal(df)
    acc = signal["accuracy"]
    if acc < 60:
        await bot.send_message(user_id, f"⚠️ Риск велик, не время торговли (точность: {acc}%)")
        return
    elif acc >= 65:
        text = (
            f"<b>📊 Сигнал по {symbol}</b>\n"
            f"Направление: <b>{signal['direction']}</b>\n"
            f"Цена входа: <b>{signal['entry']}</b>\n"
            f"🎯 TP: {signal['tp_percent']}% ({signal['tp_price']})\n"
            f"🛑 SL: {signal['sl_percent']}% ({signal['sl_price']})\n"
            f"🎯 Точность прогноза: <b>{acc}%</b>"
        )
        await bot.
send_message(user_id, text)

        # Проверка на пробитие TP/SL (эмуляция)
        current_price = df["close"].iloc[-1]
        if (signal["direction"] == "Buy" and current_price >= signal["tp_price"]) or \
           (signal["direction"] == "Sell" and current_price <= signal["tp_price"]):
            await bot.send_message(user_id, "✅ TP достигнут!")
        elif (signal["direction"] == "Buy" and current_price <= signal["sl_price"]) or \
             (signal["direction"] == "Sell" and current_price >= signal["sl_price"]):
            await bot.send_message(user_id, "❌ SL сработал!")

# === ХЭНДЛЕРЫ ===
@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id
    current_asset[user_id] = "BTCUSDT"
    await message.answer("🧠 <b>Пора выбраться из матрицы</b>", reply_markup=keyboard)

@dp.message(F.text.startswith("📈 Актив:"))
async def change_asset(message: types.Message):
    asset = message.text.replace("📈 Актив: ", "").strip()
    user_id = message.from_user.id
    if asset in ASSETS:
        current_asset[user_id] = asset
        await message.answer(f"✅ Актив установлен: {asset}")

@dp.message(F.text.startswith("⏰ Время торговли"))
async def set_schedule(message: types.Message):
    user_id = message.from_user.id
    asset = current_asset.get(user_id, "BTCUSDT")
    try:
        await message.answer(f"Введите время в формате HH:MM-HH:MM для {asset}")
    except:
        await message.answer("❌ Ошибка при установке времени.")

@dp.message(F.text.contains(":") & F.text.contains("-"))
async def handle_time_input(message: types.Message):
    user_id = message.from_user.id
    asset = current_asset.get(user_id, "BTCUSDT")
    try:
        start, end = message.text.strip().split("-")
        datetime.strptime(start, "%H:%M")
        datetime.strptime(end, "%H:%M")
        SCHEDULE[asset] = (start, end)
        await message.answer(f"✅ Время торговли для {asset} установлено: {start}-{end}")
    except:
        await message.answer("❌ Неверный формат. Пример: 09:00-17:00")

@dp.message(F.text == "🔄 Получить сигнал")
async def manual_signal(message: types.Message):
    user_id = message.from_user.id
    asset = current_asset.get(user_id, "BTCUSDT")
    await send_signal(user_id, asset)

# === АВТОСИГНАЛ ===
async def autosignal_loop():
    while True:
        for user_id, asset in current_asset.items():
            df = fetch_data(asset)
            if df is not None:
                signal = predict_signal(df)
                if signal["accuracy"] >= 70:
                    await send_signal(user_id, asset)
        await asyncio.sleep(300)  # Проверка каждые 5 минут

# === ЗАПУСК ===
async def main():
    asyncio.create_task(autosignal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
