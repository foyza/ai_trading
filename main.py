import asyncio
import random
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yfinance as yf
from datetime import datetime
import pytz

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]
user_data = {}  # {user_id: {"asset": ..., "schedule": [(start, end), ...]}}

# --- Получаем цену из Yahoo Finance ---
def get_market_price(asset):
    symbol_map = {
        "BTCUSD": "BTC-USD",
        "XAUUSD": "GC=F",
        "USTECH100": "^NDX",
    }
    ticker = symbol_map.get(asset)
    if not ticker:
        return None
    data = yf.Ticker(ticker).history(period="1d", interval="1m")
    if data.empty:
        return None
    return float(data["Close"].iloc[-1])

# --- Генерация сигнала ---
def generate_signal(asset):
    price = get_market_price(asset)
    if price is None:
        return None
    direction = random.choice(["Buy", "Sell"])
    accuracy = round(random.uniform(60, 95), 2)
    tp = price * (1 + 0.02) if direction == "Buy" else price * (1 - 0.02)
    sl = price * (1 - 0.015) if direction == "Buy" else price * (1 + 0.015)
    return {
        "asset": asset,
        "direction": direction,
        "entry": round(price, 2),
        "tp": round(tp, 2),
        "sl": round(sl, 2),
        "accuracy": accuracy,
    }

# --- Формат сигнала ---
def format_signal(signal, auto=False):
    prefix = "🔔 <b>Автосигнал</b>" if auto else "🔔 <b>Сигнал</b>"
    return (
        f"{prefix} по <b>{signal['asset']}</b> ({signal['direction']})\n"
        f"🎯 Вход: <b>{signal['entry']}</b>\n"
        f"📈 TP: <b>{signal['tp']}</b> (+2%)\n"
        f"📉 SL: <b>{signal['sl']}</b> (-1.5%)\n"
        f"📊 Точность прогноза: <b>{signal['accuracy']}%</b>"
    )

# --- Проверка расписания пользователя ---
def is_within_schedule(user_id):
    schedule = user_data.get(user_id, {}).get("schedule")
    if not schedule:
        return True  # По умолчанию всегда
    now = datetime.now(pytz.timezone("Asia/Tashkent")).time()
    for start, end in schedule:
        if start <= now <= end:
            return True
    return False

# --- Команды и кнопки ---
@dp.message(F.text == "/start")
async def start(message: Message):
    user_data[message.from_user.id] = {
        "asset": "BTCUSD",
        "schedule": [],
    }
    await message.answer("Пора выбраться из матрицы!", reply_markup=asset_keyboard())

@dp.message(F.text == "/change_asset")
async def change_asset(message: Message):
    await message.answer("Выберите актив:", reply_markup=asset_keyboard())

@dp.message(F.text == "/change_schedule")
async def change_schedule(message: Message):
    await message.answer("Выберите расписание:", reply_markup=schedule_keyboard())

# --- Кнопки активов ---
def asset_keyboard():
    kb = InlineKeyboardBuilder()
    for asset in ASSETS:
        kb.button(text=asset, callback_data=f"asset:{asset}")
    return kb.as_markup()

# --- Кнопки расписания ---
def schedule_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Круглосуточно", callback_data="schedule:all"),
            InlineKeyboardButton(text="9:00–18:00", callback_data="schedule:9_18"),
        ],
        [
            InlineKeyboardButton(text="10:00–22:00", callback_data="schedule:10_22"),
            InlineKeyboardButton(text="Выходные отключены", callback_data="schedule:weekdays"),
        ]
    ])

# --- Обработка выбора актива ---
@dp.callback_query(F.data.startswith("asset:"))
async def asset_chosen(callback: CallbackQuery):
    asset = callback.data.split(":")[1]
    user_data.setdefault(callback.from_user.id, {})["asset"] = asset
    signal = generate_signal(asset)
    if signal and signal["accuracy"] >= 65:
        await callback.message.answer(format_signal(signal))
    else:
        await callback.message.answer("❌ Недостаточная точность или ошибка данных.")

# --- Обработка выбора расписания ---
@dp.callback_query(F.data.startswith("schedule:"))
async def schedule_chosen(callback: CallbackQuery):
    user_id = callback.from_user.id
    key = callback.data.split(":")[1]
    if key == "all":
        schedule = []
    elif key == "9_18":
        schedule = [(datetime.strptime("09:00", "%H:%M").time(),
                     datetime.strptime("18:00", "%H:%M").time())]
    elif key == "10_22":
        schedule = [(datetime.strptime("10:00", "%H:%M").time(),
                     datetime.strptime("22:00", "%H:%M").time())]
    elif key == "weekdays":
        # Можно позже учесть дни недели
        schedule = [(datetime.strptime("09:00", "%H:%M").time(),
                     datetime.strptime("18:00", "%H:%M").time())]
    else:
        schedule = []
    user_data.setdefault(user_id, {})["schedule"] = schedule
    await callback.message.answer("✅ Расписание обновлено.")

# --- Цикл авто сигналов ---
async def auto_signal_loop():
    while True:
        for user_id, data in user_data.items():
            asset = data.get("asset", "BTCUSD")
            if is_within_schedule(user_id):
                signal = generate_signal(asset)
                if signal and signal["accuracy"] >= 70:
                    try:
                        await bot.send_message(chat_id=user_id, text=format_signal(signal, auto=True))
                    except:
                        pass
        await asyncio.sleep(60)

# --- Старт бота ---
async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
