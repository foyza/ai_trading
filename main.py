import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, time
import pytz
import numpy as np
import pandas as pd
import yfinance as yf
from binance.client import Client

API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
client = Client()  # Binance без API ключей
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# Состояние пользователя
user_states = {}

# Временная зона
UZ_TZ = pytz.timezone("Asia/Tashkent")

# Кнопки
main_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
main_keyboard.add(
    KeyboardButton("🔄 Получить сигнал"),
    KeyboardButton("⚙️ Изменить расписание"),
)
main_keyboard.add(
    KeyboardButton("BTCUSDT"),
    KeyboardButton("XAUUSDT"),
    KeyboardButton("NAS100"),
)

# Получение данных
def get_price_data(symbol):
    try:
        if symbol in ["BTCUSDT", "XAUUSDT"]:
            klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=100)
            if not klines or len(klines) == 0:
                print(f"[ERROR] Binance пустой для {symbol}")
                return None
            df = pd.DataFrame(klines, columns=[
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "number_of_trades",
                "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
            ])
            df["close"] = df["close"].astype(float)
            return df

        elif symbol == "NAS100":
            df = yf.download("^NDX", interval="15m", period="1d")
            if df.empty:
                print("[ERROR] yfinance пустой для NAS100")
                return None
            df = df.rename(columns={"Close": "close"})
            return df

    except Exception as e:
        print(f"[ERROR] Ошибка при получении {symbol}: {e}")
        return None

# Эмуляция сигнала
def generate_signal(df):
    direction = np.random.choice(["Buy", "Sell"])
    entry = df["close"].iloc[-1]
    acc = round(np.random.uniform(50, 90), 2)
    tp_percent, sl_percent = 1.5, 1
    tp_price = entry * (1 + tp_percent/100) if direction == "Buy" else entry * (1 - tp_percent/100)
    sl_price = entry * (1 - sl_percent/100) if direction == "Buy" else entry * (1 + sl_percent/100)
    return {
        "direction": direction,
        "entry": round(entry, 2),
        "tp_percent": tp_percent,
        "sl_percent": sl_percent,
        "tp_price": round(tp_price, 2),
        "sl_price": round(sl_price, 2),
        "accuracy": acc
    }

# Проверка расписания
def is_within_schedule(user_id, symbol):
    now = datetime.now(UZ_TZ).time()
    schedule = user_states.get(user_id, {}).get("schedule", {}).get(symbol, "00:00-23:59")
    try:
        start_str, end_str = schedule.split("-")
        start = time.fromisoformat(start_str)
        end = time.fromisoformat(end_str)
        return start <= now <= end
    except:
        return True  # по умолчанию круглосуточно

# Команда /start
@dp.message(commands=["start"])
async def start(message: types.Message):
    user_states[message.chat.id] = {
        "symbol": "BTCUSDT",
        "schedule": {
            "BTCUSDT": "00:00-23:59",
            "XAUUSDT": "00:00-23:59",
            "NAS100": "00:00-23:59"
        }
    }
    await message.answer("Пора выбраться из матрицы", reply_markup=main_keyboard)

# Обработка кнопок
@dp.message()
async def handle_buttons(message: types.Message):
    user_id = message.chat.id
    text = message.text

    if text in ["BTCUSDT", "XAUUSDT", "NAS100"]:
        user_states[user_id]["symbol"] = text
        await message.answer(f"📈 Актив установлен: {text}")

    elif text == "🔄 Получить сигнал":
        await handle_signal_request(message)

    elif text == "⚙️ Изменить расписание":
        await message.answer("Введите расписание в формате 09:00-17:00 для текущего актива.")

    elif "-" in text and ":" in text:
        symbol = user_states[user_id]["symbol"]
        user_states[user_id]["schedule"][symbol] = text
        await message.answer(f"🕒 Время торговли для {symbol} установлено: {text}")

# Обработка сигнала
async def handle_signal_request(message):
    user_id = message.chat.id
    symbol = user_states.get(user_id, {}).get("symbol", "BTCUSDT")

    if not is_within_schedule(user_id, symbol):
        await message.answer("⚠️ Сейчас не входит в торговое время.")
        return

    df = get_price_data(symbol)
    if df is None:
        await message.answer(f"⚠️ Данные по {symbol} не получены.")
        return

    signal = generate_signal(df)
    acc = signal["accuracy"]

    if acc < 60:
        await message.answer(f"⚠️ Риск велик, не время торговли ({acc}%)")
        return
    elif acc < 65:
        await message.answer(f"📉 Недостаточная точность: {acc}%. Сигнал не отправлен.")
        return

    # Отправка сигнала
    msg = (
        f"<b>📊 Сигнал по {symbol}</b>\n"
        f"Направление: <b>{signal['direction']}</b>\n"
        f"Цена входа: <b>{signal['entry']}</b>\n"
        f"🎯 TP: {signal['tp_percent']}% ({signal['tp_price']})\n"
        f"🛑 SL: {signal['sl_percent']}% ({signal['sl_price']})\n"
        f"🎯 Точность прогноза: <b>{acc}%</b>"
    )
    await message.answer(msg)

    # Проверка TP/SL
    current_price = df["close"].iloc[-1]
    if (signal["direction"] == "Buy" and current_price >= signal["tp_price"]) or \
       (signal["direction"] == "Sell" and current_price <= signal["tp_price"]):
        await message.answer("✅ TP достигнут!")
    elif (signal["direction"] == "Buy" and current_price <= signal["sl_price"]) or \
         (signal["direction"] == "Sell" and current_price >= signal["sl_price"]):
        await message.answer("❌ SL сработал!")

# Автосигналы при >70%
async def auto_signal_loop():
    while True:
        for user_id in user_states:
            symbol = user_states[user_id]["symbol"]
            if not is_within_schedule(user_id, symbol):
                continue
            df = get_price_data(symbol)
            if df is None:
                continue
            signal = generate_signal(df)
            acc = signal["accuracy"]
            if acc >= 70:
                msg = (
                    f"<b>📊 Сигнал по {symbol}</b>\n"
                    f"Направление: <b>{signal['direction']}</b>\n"
                    f"Цена входа: <b>{signal['entry']}</b>\n"
                    f"🎯 TP: {signal['tp_percent']}% ({signal['tp_price']})\n"
                    f"🛑 SL: {signal['sl_percent']}% ({signal['sl_price']})\n"
                    f"🎯 Точность прогноза: <b>{acc}%</b>"
                )
                await bot.send_message(chat_id=user_id, text=msg)

                # Проверка TP/SL
                current_price = df["close"].iloc[-1]
                if (signal["direction"] == "Buy" and current_price >= signal["tp_price"]) or \
                   (signal["direction"] == "Sell" and current_price <= signal["tp_price"]):
                    await bot.send_message(user_id, "✅ TP достигнут!")
                elif (signal["direction"] == "Buy" and current_price <= signal["sl_price"]) or \
                     (signal["direction"] == "Sell" and current_price >= signal["sl_price"]):
                    await bot.send_message(user_id, "❌ SL сработал!")

        await asyncio.sleep(60)  # Проверка каждую минуту

# Запуск
async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
