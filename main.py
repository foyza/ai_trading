import asyncio
import logging
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from datetime import datetime
import httpx

# === НАСТРОЙКИ ===
API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVE_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"
assets = {
    "BTCUSD": "BTC/USD",
    "XAUUSD": "XAU/USD",
    "USTECH100": "NDX/USD"
}
user_state = {}

# === ЛОГГИРОВАНИЕ ===
logging.basicConfig(level=logging.INFO)

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# === КНОПКИ ===
main_kb = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
        [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
        [KeyboardButton(text="📅 Статус")]
    ]
)

# === ВСПОМОГАТЕЛЬНЫЕ ===
def get_user_asset(uid): return user_state.get(uid, {}).get("asset", "BTCUSD")
def is_muted(uid): return user_state.get(uid, {}).get("muted", False)
def get_schedule(uid): return user_state.get(uid, {}).get("schedule", {"Mon": [0, 24], "Tue": [0, 24], "Wed": [0, 24], "Thu": [0, 24], "Fri": [0, 24], "Sat": [0, 24], "Sun": [0, 24]})

def check_schedule(uid):
    now = datetime.utcnow()
    day = now.strftime("%a")
    hour = now.hour
    schedule = get_schedule(uid)
    if day in schedule:
        start, end = schedule[day]
        return start <= hour < end
    return False

async def fetch_data_twelvedata(symbol):
    interval = "15min"
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey={TWELVE_API_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        data = r.json()
    if "values" not in data:
        return None
    df = pd.DataFrame(data["values"])
    df = df.rename(columns={"datetime": "time", "close": "close"}).sort_values("time")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna()

def analyze(df):
    df["MA10"] = df["close"].rolling(10).mean()
    df["MA50"] = df["close"].rolling(50).mean()
    df["RSI"] = compute_rsi(df["close"], 14)
    df["MACD"] = df["close"].ewm(12).mean() - df["close"].ewm(26).mean()
    df["MACD_signal"] = df["MACD"].ewm(9).mean()

    last = df.iloc[-1]
    signals = {
        "MA": "Buy" if last["MA10"] > last["MA50"] else "Sell",
        "RSI": "Buy" if last["RSI"] < 30 else "Sell" if last["RSI"] > 70 else "Hold",
        "MACD": "Buy" if last["MACD"] > last["MACD_signal"] else "Sell"
    }

    votes = list(signals.values())
    buy_count = votes.count("Buy")
    sell_count = votes.count("Sell")

    if buy_count == 3:
        direction = "Buy"
        accuracy = 80
    elif sell_count == 3:
        direction = "Sell"
        accuracy = 80
    elif buy_count >= 2:
        direction = "Buy"
        accuracy = 65
    elif sell_count >= 2:
        direction = "Sell"
        accuracy = 65
    else:
        direction = "Hold"
        accuracy = 50

    entry = last["close"]
    tp = round(entry * (1.02 if direction == "Buy" else 0.98), 2)
    sl = round(entry * (0.98 if direction == "Buy" else 1.02), 2)

    return {
        "direction": direction,
        "accuracy": accuracy,
        "entry": entry,
        "tp": tp,
        "sl": sl
    }

def compute_rsi(series, period):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

async def send_signal(uid, asset):
    if not check_schedule(uid):
        return

    symbol = assets.get(asset, "BTC/USD")
    df = await fetch_data_twelvedata(symbol)
    if df is None:
        await bot.send_message(uid, "⚠️ Ошибка получения данных.")
        return

    signal = analyze(df)
    direction = signal["direction"]
    accuracy = signal["accuracy"]

    if direction == "Hold" or accuracy < 60:
        await bot.send_message(uid, f"⚠️ Риск велик, не время торговли (точность: {accuracy}%)")
        return

    text = f"""<b>📡 Торговый сигнал ({asset})</b>
🔁 Направление: <b>{direction}</b>
🎯 Вход: <b>{signal['entry']:.2f}</b>
🎯 TP: <b>{signal['tp']} ({'+2%' if direction == 'Buy' else '-2%'})</b>
🛡️ SL: <b>{signal['sl']} ({'-2%' if direction == 'Buy' else '+2%'})</b>
📈 Точность: <b>{accuracy}%</b>"""

    await bot.send_message(uid, text, disable_notification=is_muted(uid))

# === ХЭНДЛЕРЫ ===
@dp.message(CommandStart())
async def start(msg: types.Message):
    uid = msg.from_user.id
    user_state[uid] = {"asset": "BTCUSD", "muted": False}
    await msg.answer("🧠 Пора выбраться из матрицы", reply_markup=main_kb)

@dp.message()
async def handler(msg: types.Message):
    uid = msg.from_user.id
    text = msg.text.strip()

    if uid not in user_state:
        user_state[uid] = {"asset": "BTCUSD", "muted": False}

    if text == "🔄 Получить сигнал":
        asset = get_user_asset(uid)
        await send_signal(uid, asset)

    elif text in ["BTCUSD", "XAUUSD", "USTECH100"]:
        user_state[uid]["asset"] = text
        await msg.answer(f"✅ Актив выбран: {text}")

    elif text == "🔕 Mute":
        user_state[uid]["muted"] = True
        await msg.answer("🔇 Оповещения отключены")

    elif text == "🔔 Unmute":
        user_state[uid]["muted"] = False
        await msg.answer("🔔 Оповещения включены")

    elif text == "📅 Статус":
        schedule = get_schedule(uid)
        status = "\n".join([f"{day}: {hours[0]}–{hours[1]} UTC" for day, hours in schedule.items()])
        await msg.answer(f"📅 Ваше расписание:\n{status}")

# === АВТОСИГНАЛ ===
async def autosignal():
    while True:
        for uid, state in user_state.items():
            asset = get_user_asset(uid)
            signal = await fetch_data_twelvedata(assets[asset])
            if signal is None:
                continue
            res = analyze(signal)
            if res["accuracy"] >= 70 and res["direction"] != "Hold":
                await send_signal(uid, asset)
        await asyncio.sleep(900)

# === ЗАПУСК ===
async def main():
    asyncio.create_task(autosignal())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
