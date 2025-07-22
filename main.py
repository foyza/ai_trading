import asyncio
import httpx
import numpy as np
import pandas as pd
import ta
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import CommandStart

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
        "outputsize": 150,
        "apikey": API_KEY
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://api.twelvedata.com/time_series", params=params)
    return r.json()

def prepare_dataframe(data):
    df = pd.DataFrame(data["values"])
    df = df.iloc[::-1]  # Старые — вверху
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.astype(float)
    return df

def apply_indicators(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    return df

def get_signal(df):
    last = df.iloc[-1]
    signal = "Hold"
    votes = 0

    # RSI: <30 перепродан, >70 перекуплен
    if last["rsi"] < 35:
        votes += 1
        signal = "Buy"
    elif last["rsi"] > 65:
        votes += 1
        signal = "Sell"

    # MACD пересек снизу — Buy, сверху — Sell
    if last["macd"] > last["macd_signal"]:
        votes += 1
        signal = "Buy"
    elif last["macd"] < last["macd_signal"]:
        votes += 1
        signal = "Sell"

    # Цена возле Bollinger
    if last["close"] <= last["bb_lower"]:
        votes += 1
        signal = "Buy"
    elif last["close"] >= last["bb_upper"]:
        votes += 1
        signal = "Sell"

    return signal, votes

def calc_tp_sl(price, direction, tp_pct=0.8, sl_pct=0.6):
    if direction == "Buy":
        tp = round(price * (1 + tp_pct / 100), 4)
        sl = round(price * (1 - sl_pct / 100), 4)
    else:
        tp = round(price * (1 - tp_pct / 100), 4)
        sl = round(price * (1 + sl_pct / 100), 4)
    return tp, sl

def backtest_signal(df, direction, tp_pct=0.8, sl_pct=0.6):
    success = 0
    total = 0
    for i in range(len(df) - 1):
        entry = df["close"].iloc[i]
        high = df["high"].iloc[i + 1]
        low = df["low"].iloc[i + 1]
        if direction == "Buy":
            tp = entry * (1 + tp_pct / 100)
            sl = entry * (1 - sl_pct / 100)
            if low <= sl:
                continue
            elif high >= tp:
                success += 1
        elif direction == "Sell":
            tp = entry * (1 - tp_pct / 100)
            sl = entry * (1 + sl_pct / 100)
            if high >= sl:
                continue
            elif low <= tp:
                success += 1
        total += 1
    return round((success / total) * 100, 1) if total > 0 else 0.0

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    uid = msg.from_user.id
    user_settings[uid] = {
        "asset": symbols[0],
        "mute": False,
        "strategy": strategies[0],
        "schedule": []
    }
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
        if "values" not in data:
            return await msg.answer("❌ Ошибка получения данных.")
        df = prepare_dataframe(data)
        df = apply_indicators(df)
        signal, votes = get_signal(df)
        price = df["close"].iloc[-1]
        if signal == "Hold":
            return await msg.answer("⏸️ Нет чёткого сигнала. Тренд не определён.")
        tp, sl = calc_tp_sl(price, signal)
        accuracy = backtest_signal(df[-100:], signal)
        return await msg.answer(
            f"📈 Сигнал по {st['asset']}:\n"
            f"📍 {signal}\n"
            f"💰 Цена: {price:.4f}\n"
            f"🎯 TP → {tp}\n"
            f"🛑 SL → {sl}\n"
            f"📊 Точность сигнала по истории: {accuracy}%"
        )

    if text in [s.replace("/", "") for s in symbols]:
        st["asset"] = f"{text[:3]}/{text[3:]}"
        return await msg.answer(f"✅ Актив: {st['asset']}")
    if text == "🔕 Mute":
        st["mute"] = True
        return await msg.answer("🔕 Уведомления отключены.")
    if text == "🔔 Unmute":
        st["mute"] = False
        return await msg.answer("🔔 Уведомления включены.")
    if text == "🎯 Стратегия":
        return await msg.answer("📌 Стратегия: Scalping")
    if text == "📊 Статус":
        mute = "🔕" if st["mute"] else "🔔"
        return await msg.answer(
            f"📊 Настройки:\n"
            f"Актив: {st['asset']}\n"
            f"Стратегия: {st['strategy']}\n"
            f"Уведомления: {mute}"
        )
    if text == "🕒 Расписание":
        return await msg.answer("🕒 Расписание — в разработке.")

async def auto_signal_loop():
    while True:
        for uid, st in user_settings.items():
            if st["mute"]:
                continue
            data = await fetch_data(st["asset"])
            if "values" not in data:
                continue
            df = prepare_dataframe(data)
            df = apply_indicators(df)
            signal, votes = get_signal(df)
            if signal == "Hold":
                continue
            price = df["close"].iloc[-1]
            tp, sl = calc_tp_sl(price, signal)
            accuracy = backtest_signal(df[-100:], signal)
            if accuracy >= 70:
                await bot.send_message(uid,
                    f"📢 Автосигнал по {st['asset']}:\n"
                    f"📍 {signal} @ {price:.4f}\n"
                    f"🎯 TP → {tp}\n"
                    f"🛑 SL → {sl}\n"
                    f"📊 Историческая точность: {accuracy}%"
                )
        await asyncio.sleep(900)  # каждые 15 минут

async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
