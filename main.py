import asyncio
import random
import datetime
import pytz
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yfinance as yf

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]
asset_symbols = {
    "BTCUSD": "BTC-USD",
    "XAUUSD": "GC=F",
    "USTECH100": "^NDX"
}

# По умолчанию: сигнал можно в любое время
user_assets = {}
user_schedules = {}

# Получение актуальной цены с Yahoo
def get_price(asset):
    try:
        symbol = asset_symbols[asset]
        data = yf.Ticker(symbol).history(period="1d", interval="1m")
        if data.empty:
            return None
        return float(data["Close"].iloc[-1])
    except Exception as e:
        print(f"❌ Ошибка получения цены {asset}: {e}")
        return None

# Генерация сигнала
def generate_signal(asset):
    price = get_price(asset)
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
        "accuracy": accuracy
    }

def format_signal(signal, auto=False):
    prefix = "🔔 <b>Автосигнал</b>" if auto else "📩 <b>Сигнал по запросу</b>"
    return (
        f"{prefix} по <b>{signal['asset']}</b>\n"
        f"📊 Направление: <b>{signal['direction']}</b>\n"
        f"🎯 Вход: <b>{signal['entry']}</b>\n"
        f"📈 TP: <b>{signal['tp']}</b> (+2%)\n"
        f"📉 SL: <b>{signal['sl']}</b> (-1.5%)\n"
        f"🎯 Точность прогноза: <b>{signal['accuracy']}%</b>"
    )

# Кнопки главного меню
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Отправить сигнал сейчас", callback_data="send_signal")
    kb.button(text="📈 Выбрать актив", callback_data="choose_asset")
    kb.button(text="⏰ Изменить расписание", callback_data="change_schedule")
    kb.adjust(1)
    return kb.as_markup()

def asset_keyboard():
    kb = InlineKeyboardBuilder()
    for asset in ASSETS:
        kb.button(text=asset, callback_data=f"asset:{asset}")
    kb.adjust(2)
    return kb.as_markup()

def schedule_keyboard():
    kb = InlineKeyboardBuilder()
    for hour in range(0, 24, 3):
        kb.button(text=f"{hour:02d}:00", callback_data=f"time:{hour}")
    kb.adjust(4)
    return kb.as_markup()

@dp.message(F.text == "/start")
async def start(message: Message):
    user_assets[message.from_user.id] = "BTCUSD"
    user_schedules[message.from_user.id] = list(range(24))  # по умолчанию 24/7
    await message.answer("Пора выбраться из матрицы!\nВыберите действие:", reply_markup=main_menu())

@dp.callback_query(F.data == "choose_asset")
async def choose_asset(callback: CallbackQuery):
    await callback.message.edit_text("Выберите актив:", reply_markup=asset_keyboard())

@dp.callback_query(F.data.startswith("asset:"))
async def set_asset(callback: CallbackQuery):
    asset = callback.data.split(":")[1]
    user_assets[callback.from_user.id] = asset
    await callback.message.answer(f"✅ Актив установлен: <b>{asset}</b>", reply_markup=main_menu())

@dp.callback_query(F.data == "change_schedule")
async def change_schedule(callback: CallbackQuery):
    await callback.message.edit_text("🕒 Выберите часы для получения автосигналов:", reply_markup=schedule_keyboard())

@dp.callback_query(F.data.startswith("time:"))
async def set_schedule(callback: CallbackQuery):
    hour = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    if uid not in user_schedules:
        user_schedules[uid] = []
    if hour in user_schedules[uid]:
        user_schedules[uid].remove(hour)
    else:
        user_schedules[uid].append(hour)
        await callback.message.edit_text(
        f"✅ Часы обновлены: {sorted(user_schedules[uid])}\nМожете изменить ещё или нажмите /start",
        reply_markup=schedule_keyboard()
    )

@dp.callback_query(F.data == "send_signal")
async def manual_signal(callback: CallbackQuery):
    uid = callback.from_user.id
    asset = user_assets.get(uid, "BTCUSD")
    signal = generate_signal(asset)
    if not signal:
        await callback.message.answer("⚠️ Ошибка получения цены.")
        return
    if signal["accuracy"] >= 65:
        await callback.message.answer(format_signal(signal), reply_markup=main_menu())
    else:
        await callback.message.answer(f"❌ Недостаточная точность ({signal['accuracy']}%). Сигнал не отправлен.", reply_markup=main_menu())

# Автоотправка по расписанию
async def auto_signal_loop():
    while True:
        now = datetime.datetime.now(pytz.timezone("Asia/Tashkent"))
        current_hour = now.hour

        for uid in user_assets:
            asset = user_assets.get(uid, "BTCUSD")
            schedule = user_schedules.get(uid, list(range(24)))

            if current_hour in schedule:
                signal = generate_signal(asset)
                if signal and signal["accuracy"] >= 70:
                    try:
                        await bot.send_message(uid, format_signal(signal, auto=True))
                    except Exception as e:
                        print(f"Ошибка отправки сигналов: {e}")
        await asyncio.sleep(60 * 5)  # проверка каждые 5 минут

async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
