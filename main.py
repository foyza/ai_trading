import os
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.markdown import hbold

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"  

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Активы
TRADABLE_ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]

# Временное хранилище расписаний
user_trading_hours = {}

# Проверка доступности сигнала по расписанию
def is_tradable_now(asset: str, user_id: int):
    now = datetime.utcnow()
    hour = now.hour
    weekday = now.weekday()

    if user_id in user_trading_hours and asset in user_trading_hours[user_id]:
        hours = user_trading_hours[user_id][asset].get("hours", (0, 24))
        days = user_trading_hours[user_id][asset].get("days", list(range(7)))
    else:
        # По умолчанию: BTC — все дни, остальные — по будням
        if asset == "BTCUSD":
            hours, days = (0, 24), list(range(7))
        else:
            hours, days = (0, 24), list(range(0, 5))

    return hour >= hours[0] and hour < hours[1] and weekday in days

# Команда: установить часы торговли
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

# Команда: установить дни недели
@dp.message(Command("setdays"))
async def set_days_cmd(msg: types.Message):
    parts = msg.text.split()
    if len(parts) < 3:
        await msg.answer("Формат: /setdays ASSET day1 day2 ...\nПример: /setdays BTCUSD 0 1 2 3 4 5 6")
        return

    asset = parts[1]
    if asset not in TRADABLE_ASSETS:
        await msg.answer("⛔️ Недопустимый актив.")
        return

    try:
        days = list(map(int, parts[2:]))
    except ValueError:
        await msg.answer("❗️Дни должны быть числами от 0 (Пн) до 6 (Вс)")
        return

    user_id = msg.from_user.id
    if user_id not in user_trading_hours:
        user_trading_hours[user_id] = {}
    if asset not in user_trading_hours[user_id]:
        user_trading_hours[user_id][asset] = {}
    user_trading_hours[user_id][asset]["days"] = days

    await msg.answer(f"✅ Дни торговли для {asset} установлены: {', '.join(map(str, days))}")

# Команда: запросить сигнал
@dp.message(Command("signal"))
async def send_signal(msg: types.Message):
    parts = msg.text.split()
    if len(parts) != 2:
        await msg.answer("Формат: /signal ASSET")
        return

    asset = parts[1]
    user_id = msg.from_user.id

    if not is_tradable_now(asset, user_id):
        await msg.answer("⛔️ Сейчас не торговое время для этого актива.")
        return

    # ⚠️ Вставь здесь свою модель предсказания
    prediction, accuracy = "Buy", 0.82
    stop_loss, take_profit = "50", "150"
    image_path = "chart_placeholder.jpg"

    if accuracy < 0.7:
        await msg.answer("⚠️ Недостаточно данных для точного прогноза.")
        return

    text = (
        f"{hbold(asset)} сигнал: {prediction}\n"
        f"🎯 Take Profit: {take_profit}\n"
        f"🛑 Stop Loss: {stop_loss}\n"
        f"📈 Точность: {accuracy * 100:.1f}%"
    )

    try:
        with open(image_path, "rb") as img:
            await msg.answer_photo(img, caption=text)
    except FileNotFoundError:
        await msg.answer(text + "\n⚠️ График не найден.")

# Запуск
async def main():
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)

if name == "__main__":
    asyncio.run(main())
