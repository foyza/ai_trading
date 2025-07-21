import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVE_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

user_data = defaultdict(lambda: {
    "asset": "BTCUSD",
    "muted": False,
    "strategy": "MA+RSI+MACD",
    "schedule": "24/7"
})

ASSET_SYMBOLS = {
    "BTCUSD": "BTC/USD",
    "XAUUSD": "XAU/USD",
    "USTECH100": "NAS100"
}

buttons = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔄 Получить сигнал")],
    [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
    [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
    [KeyboardButton(text="🎯 Стратегия"), KeyboardButton(text="🕒 Расписание")],
    [KeyboardButton(text="📊 Статус")]
], resize_keyboard=True)

# ---------------------- API DATA FETCH ----------------------
async def fetch_data(asset):
    interval = "15min"
    url = f"https://api.twelvedata.com/time_series?symbol={ASSET_SYMBOLS[asset]}&interval={interval}&apikey={TWELVE_API_KEY}&outputsize=100"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            if "values" in data:
                df = pd.DataFrame(data["values"])
                df = df.astype({"open": float, "close": float, "high": float, "low": float})
                df["datetime"] = pd.to_datetime(df["datetime"])
                df.sort_values("datetime", inplace=True)
                return df
            else:
                return None

# ---------------------- INDICATORS ----------------------
def calculate_indicators(df):
    df["MA10"] = df["close"].rolling(10).mean()
    df["MA50"] = df["close"].rolling(50).mean()
    delta = df["close"].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=14).mean()
    avg_loss = pd.Series(loss).rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    exp1 = df["close"].ewm(span=12, adjust=False).mean()
    exp2 = df["close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = exp1 - exp2
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

    return df

def generate_signal(df):
    latest = df.iloc[-1]
    ma_signal = "Buy" if latest["MA10"] > latest["MA50"] else "Sell"
    rsi_signal = "Buy" if latest["RSI"] < 30 else "Sell" if latest["RSI"] > 70 else "Hold"
    macd_signal = "Buy" if latest["MACD"] > latest["Signal"] else "Sell"

    signals = [ma_signal, rsi_signal, macd_signal]
    buy_count = signals.count("Buy")
    sell_count = signals.count("Sell")

    if buy_count == 3:
        return "Buy", 78
    elif sell_count == 3:
        return "Sell", 78
    elif buy_count == 2 or sell_count == 2:
        return "Hold", 65
    return "None", 55

def build_signal_text(asset, direction, price, tp, sl, accuracy):
    tp_price = round(price * (1 + tp/100) if direction == "Buy" else price * (1 - tp/100), 2)
    sl_price = round(price * (1 - sl/100) if direction == "Buy" else price * (1 + sl/100), 2)
    return (f"<b>{asset} | {direction}</b>\n"
            f"🎯 Вход: <b>{price}</b>\n"
            f"📈 TP: <b>{tp}%</b> → {tp_price}\n"
            f"📉 SL: <b>{sl}%</b> → {sl_price}\n"
            f"🎯 Точность: <b>{accuracy}%</b>")

# ---------------------- HANDLERS ----------------------
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    await msg.answer("Пора выбраться из матрицы", reply_markup=buttons)

@dp.message(F.text.in_(["BTCUSD", "XAUUSD", "USTECH100"]))
async def set_asset(msg: types.Message):
    user_data[msg.from_user.id]["asset"] = msg.text
    await msg.answer(f"✅ Актив выбран: {msg.text}")

@dp.message(F.text == "🔕 Mute")
async def mute_user(msg: types.Message):
    user_data[msg.from_user.id]["muted"] = True
    await msg.answer("🔕 Уведомления отключены")

@dp.message(F.text == "🔔 Unmute")
async def unmute_user(msg: types.Message):
    user_data[msg.from_user.id]["muted"] = False
    await msg.answer("🔔 Уведомления включены")

@dp.message(F.text == "🎯 Стратегия")
async def change_strategy(msg: types.Message):
    old = user_data[msg.from_user.id]["strategy"]
    user_data[msg.from_user.id]["strategy"] = "Bollinger+Volume" if old == "MA+RSI+MACD" else "MA+RSI+MACD"
    await msg.answer(f"🎯 Стратегия установлена: {user_data[msg.from_user.id]['strategy']}")

@dp.message(F.text == "📊 Статус")
async def show_status(msg: types.Message):
    data = user_data[msg.from_user.id]
    text = (
        f"<b>Ваши настройки:</b>\n"
        f"Актив: {data['asset']}\n"
        f"Стратегия: {data['strategy']}\n"
        f"Уведомления: {'🔕 Mute' if data['muted'] else '🔔 Unmute'}\n"
        f"Расписание: {data['schedule']}"
    )
    await msg.answer(text)

@dp.message(F.text == "🔄 Получить сигнал")
async def manual_signal(msg: types.Message):
    uid = msg.from_user.id
    asset = user_data[uid]["asset"]
    df = await fetch_data(asset)
    if df is None:
        return await msg.answer("❌ Не удалось загрузить данные")

    df = calculate_indicators(df)
    signal, accuracy = generate_signal(df)
    price = round(df["close"].iloc[-1], 2)

    if signal in ["Buy", "Sell"] and accuracy >= 65:
        text = build_signal_text(asset, signal, price, 2.0, 1.0, accuracy)
        await msg.answer(text)
    elif accuracy < 60:
        await msg.answer(f"⚠️ Риск велик, не время торговли (точность: {accuracy}%)")
    else:
        await msg.answer("⏳ Недостаточно точный сигнал")

# ---------------------- AUTO SIGNALS ----------------------
async def auto_signal_loop():
    while True:
        for uid, data in user_data.items():
            if data["muted"]:
                continue
            df = await fetch_data(data["asset"])
            if df is None:
                continue
            df = calculate_indicators(df)
            signal, accuracy = generate_signal(df)
            if signal in ["Buy", "Sell"] and accuracy >= 70:
                price = round(df["close"].iloc[-1], 2)
                text = build_signal_text(data["asset"], signal, price, 2.0, 1.0, accuracy)
                try:
                    await bot.send_message(uid, text)
                except:
                    pass
        await asyncio.sleep(900)  # каждые 15 мин

# ---------------------- MAIN ----------------------
async def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
