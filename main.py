import asyncio
import random
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import matplotlib.pyplot as plt
import os

import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# --- Конфигурация ---
import os
TOKEN = os.getenv("8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA")
AUTO_SIGNAL_INTERVAL = 900  # 15 минут
USER_REQUEST_LIMIT = 2
USER_REQUEST_WINDOW = 300  # 5 минут
DEFAULT_HOURS = (0, 24)
DEFAULT_DAYS = list(range(7))  # 0-6, понедельник-воскресенье
TRADABLE_ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]

bot = Bot(token=TOKEN)
dp = Dispatcher()
user_requests = {}
user_trading_hours = {}  # {user_id: {"BTCUSD": {"hours": (8, 21), "days": [0,1,2,3,4,5,6]}}}

# --- AI модель (заглушка) ---
def predict_signal(asset):
    accuracy = random.uniform(0.65, 0.95)
    if accuracy < 0.7:
        return {"accuracy": accuracy}

    direction = random.choice(["BUY", "SELL"])
    return {
        "direction": direction,
        "take_profit": round(random.uniform(0.5, 2.0), 2),
        "stop_loss": round(random.uniform(0.3, 1.5), 2),
        "accuracy": accuracy
    }

# --- Отрисовка графика ---
def draw_chart(asset, direction, tp, sl):
    x = list(range(10))
    y = [i + (0.1 if direction == "BUY" else -0.1) * i for i in x]

    plt.figure(figsize=(6, 3))
    plt.plot(x, y, label=direction)
    plt.axhline(y[-1] + tp, color='green', linestyle='--', label='TP')
    plt.axhline(y[-1] - sl, color='red', linestyle='--', label='SL')
    plt.title(f"{asset} Signal")
    plt.legend()

    filename = f"{asset}_chart.png"
    plt.savefig(filename)
    plt.close()
    return filename

# --- Генерация сигнала ---
async def generate_signal(asset):
    signal_data = predict_signal(asset)
    if signal_data["accuracy"] < 0.7:
        return None, None

    tp = signal_data['take_profit']
    sl = signal_data['stop_loss']
    direction = signal_data['direction']
    chart_path = draw_chart(asset, direction, tp, sl)

    signal_msg = f"📈 {asset}\n"                  f"🔹 Направление: {direction}\n"                  f"🎯 TP: {tp}\n"                  f"🛑 SL: {sl}\n"                  f"📊 Точность: {int(signal_data['accuracy'] * 100)}%"

    return signal_msg, chart_path

# --- Ограничение по ручным запросам ---
def can_user_request(user_id):
    now = time.time()
    requests = user_requests.get(user_id, [])
    requests = [r for r in requests if now - r < USER_REQUEST_WINDOW]
    if len(requests) >= USER_REQUEST_LIMIT:
        return False
    requests.append(now)
    user_requests[user_id] = requests
    return True

# --- Проверка времени торговли ---
def is_asset_active(asset, user_id):
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()

    settings = user_trading_hours.get(user_id, {}).get(asset, {})
    hours = settings.get("hours", DEFAULT_HOURS)
    days = settings.get("days", DEFAULT_DAYS)

    return hours[0] <= hour < hours[1] and weekday in days

# --- Команды Telegram ---
@dp.message(Command("start"))
async def start_cmd(msg: types.Message):
    await msg.answer("Добро пожаловать в AI трейдинг-бот!\n"
                     "Команды:\n"
                     "/signal — запросить сигнал\n"
                     "/sethours ASSET START END — часы\n"
                     "/setdays ASSET DAYS — дни (например: 0 1 2 3 4)")

@dp.message(Command("signal"))
async def signal_cmd(msg: types.Message):
    user_id = msg.from_user.id
    if not can_user_request(user_id):
        await msg.answer("⛔️ Не более 2 запросов за 5 минут.")
        return

    await msg.answer("⏳ Генерация сигнала...")
    asset = "BTCUSD"  # По умолчанию
    signal, chart = await generate_signal(asset)
    if not signal:
        await msg.answer("⚠️ Недостаточно данных для сигнала.")
        return

    await msg.answer_photo(types.FSInputFile(chart), caption=signal)

@dp.message(Command("sethours"))
async def set_hours_cmd(msg: types.Message):
    parts = msg.text.split()
    if len(parts) != 4:
        await msg.answer("Формат: /sethours ASSET START END")
        return

    asset, start, end = parts[1], int(parts[2]), int(parts[3])

    if asset not in TRADABLE_ASSETS:
        await msg.answer("⛔️ Недопустимый актив.")
        return

    user_id = msg.from_user.id
    if user_id not in user_trading_hours:
        user_trading_hours[user_id] = {}
    if asset not in user_trading_hours[user_id]:
        user_trading_hours[user_id][asset] = {}
    user_trading_hours[user_id][asset]["hours"] = (start, end)

    await msg.answer(f"✅ Часы торговли для {asset} установлены: {start}:00 - {end}:00")

@dp.message(Command("setdays"))
async def set_days_cmd(msg: types.Message):
    parts = msg.text.split()
    if len(parts) < 3:
        await msg.answer("Формат: /setdays ASSET D1 D2 D3 ... (0=Пн, 6=Вс)")
        return

    asset = parts[1]
    days = list(map(int, parts[2:]))
    user_id = msg.from_user.id

    if user_id not in user_trading_hours:
        user_trading_hours[user_id] = {}
    if asset not in user_trading_hours[user_id]:
        user_trading_hours[user_id][asset] = {}
    user_trading_hours[user_id][asset]["days"] = days

    await msg.answer(f"✅ Дни торговли для {asset} установлены: {', '.join(map(str, days))}")

# --- Автосигналы ---
async def auto_signal_loop():
    await asyncio.sleep(5)
    while True:
        now = datetime.now()
        for asset in TRADABLE_ASSETS:
            for user_id in user_trading_hours.keys():
                if is_asset_active(asset, user_id):
                    signal, chart = await generate_signal(asset)
                    if signal:
                        try:
                            await bot.send_photo(chat_id=user_id, photo=types.FSInputFile(chart), caption=signal)
                        except Exception as e:
                            print("Ошибка отправки:", e)
        await asyncio.sleep(AUTO_SIGNAL_INTERVAL)

# --- Запуск ---
async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if name == "__main__":
    asyncio.run(main())
