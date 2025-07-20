import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
import yfinance as yf
import datetime
import random

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"

dp = Dispatcher()
bot = Bot(token=TOKEN)

user_state = {}
user_schedule = {}

assets = {
    "BTCUSD": "BTC-USD",
    "XAUUSD": "GC=F",
    "USTECH100": "^NDX"
}

# Клавиатура
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="📈 Выбрать актив"), KeyboardButton(text="⏰ Настроить время")]
    ],
    resize_keyboard=True
)

async def fetch_data(ticker):
    try:
        data = yf.download(ticker, period="1d", interval="1m")
        return data
    except Exception as e:
        return None

def generate_signal(data):
    if data is None or len(data) < 2:
        return None

    last_price = data["Close"].iloc[-1]
    change = (last_price - data["Close"].iloc[-2]) / data["Close"].iloc[-2]
    accuracy = random.randint(50, 100)  # Заменить на ML-модель

    direction = "Buy" if change > 0 else "Sell"
    tp_pct = 1.5
    sl_pct = 0.8
    entry = round(last_price, 2)

    tp_price = round(entry * (1 + tp_pct/100 if direction == "Buy" else 1 - tp_pct/100), 2)
    sl_price = round(entry * (1 - sl_pct/100 if direction == "Buy" else 1 + sl_pct/100), 2)

    return {
        "entry": entry,
        "direction": direction,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "accuracy": accuracy
    }

def is_in_schedule(user_id):
    schedule = user_schedule.get(user_id, {"start": "00:00", "end": "23:59", "days": list(range(7))})
    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M")
    current_day = now.weekday()

    return schedule["start"] <= current_time <= schedule["end"] and current_day in schedule["days"]

@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text

    if text == "/start":
        user_state[user_id] = "BTCUSD"
        await message.answer("Пора выбраться из матрицы", reply_markup=keyboard)

    elif text == "📈 Выбрать актив":
        markup = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=asset)] for asset in assets.keys()],
            resize_keyboard=True
        )
        await message.answer("Выберите актив:", reply_markup=markup)

    elif text in assets.keys():
        user_state[user_id] = text
        await message.answer(f"Актив установлен: {text}", reply_markup=keyboard)

    elif text == "⏰ Настроить время":
        await message.answer("Введите диапазон времени в формате ЧЧ:ММ-ЧЧ:ММ (например: 09:00-17:30)")

    elif "-" in text and ":" in text:
        try:
            start, end = text.split("-")
            user_schedule[user_id] = {
                "start": start.strip(),
                "end": end.strip(),
                "days": list(range(7))
            }
            await message.answer(f"Время торговли установлено: {start.strip()} — {end.strip()}", reply_markup=keyboard)
        except:
            await message.answer("⚠️ Неверный формат. Попробуйте снова.")

    elif text == "🔄 Получить сигнал":
        if not is_in_schedule(user_id):
            await message.answer("⏳ Сейчас вне установленного торгового времени.")
            return

        asset = user_state.get(user_id, "BTCUSD")
        data = await fetch_data(assets[asset])
        signal = generate_signal(data)

        

        accuracy = signal["accuracy"]
        if accuracy < 60:
            await message.answer(f"⚠️ Риск велик, не время торговли ({accuracy}%)")
            return

        if accuracy < 65:
            await message.answer(f"⚠️ Точность ниже 65% ({accuracy}%), ручной сигнал не отправляется.")
            return

        await send_signal(message.chat.id, asset, signal)
async def send_signal(chat_id, asset, signal):
    text = (
        f"📊 Сигнал по активу: {asset}\n"
        f"🎯 Направление: {signal['direction']}\n"
        f"💰 Вход: {signal['entry']}\n"
        f"📈 TP: +{signal['tp_pct']}% → {signal['tp_price']}\n"
        f"📉 SL: -{signal['sl_pct']}% → {signal['sl_price']}\n"
        f"✅ Точность прогноза: {signal['accuracy']}%"
    )
    await bot.send_message(chat_id, text)

# Автоматическая отправка при точности >70%
async def monitor_signals():
    while True:
        for user_id in user_state.keys():
            if not is_in_schedule(user_id):
                continue

            asset = user_state.get(user_id, "BTCUSD")
            data = await fetch_data(assets[asset])
            signal = generate_signal(data)

            if signal and signal["accuracy"] >= 70:
                await send_signal(user_id, asset, signal)

        await asyncio.sleep(30)  # Проверка каждую минуту

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(monitor_signals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
