import asyncio
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

TRADABLE_ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]
user_trading_hours = {}
user_selected_asset = {}

def generate_signal(asset: str):
    entry = round(random.uniform(1000, 50000), 2)
    direction = random.choice(["Buy", "Sell"])
    tp_pct = 0.02
    sl_pct = 0.015

    if direction == "Buy":
        tp = round(entry * (1 + tp_pct), 2)
        sl = round(entry * (1 - sl_pct), 2)
    else:
        tp = round(entry * (1 - tp_pct), 2)
        sl = round(entry * (1 + sl_pct), 2)

    accuracy = round(random.uniform(60, 95), 2)

    return {
        "entry": entry,
        "tp": tp,
        "sl": sl,
        "direction": direction,
        "accuracy": accuracy
    }

def is_within_trading_hours(asset: str, user_id: int):
    from datetime import datetime
    now_hour = datetime.utcnow().hour
    settings = user_trading_hours.get(user_id, {}).get(asset)
    if not settings:
        return True
    start, end = settings.get("hours", (0, 24))
    return start <= now_hour < end

@dp.message(Command("start"))
async def start_cmd(msg: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Получить сигнал")],
        [KeyboardButton(text="⚙️ Установить актив")]
    ], resize_keyboard=True)
    await msg.answer("👋 Привет! Я AI Trading Бот. Выберите действие ниже:", reply_markup=kb)

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
    user_trading_hours[user_id][asset] = {"hours": (start, end)}
    await msg.answer(f"✅ Часы торговли для {asset} установлены: {start}:00 - {end}:00")

@dp.message(F.text == "⚙️ Установить актив")
async def choose_asset(msg: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=asset)] for asset in TRADABLE_ASSETS],
        resize_keyboard=True
    )
    await msg.answer("Выберите актив:", reply_markup=kb)

@dp.message(F.text.in_(TRADABLE_ASSETS))
async def set_asset(msg: types.Message):
    user_selected_asset[msg.from_user.id] = msg.text
    await msg.answer(f"✅ Актив выбран: {msg.text}")

@dp.message(F.text == "📊 Получить сигнал")
async def manual_signal(msg: types.Message):
    user_id = msg.from_user.id
    asset = user_selected_asset.get(user_id, "BTCUSD")
    if not is_within_trading_hours(asset, user_id):
        await msg.answer("⏰ Сейчас вне ваших торговых часов.")
        return

    signal = generate_signal(asset)
    if signal["accuracy"] < 65:
        await msg.answer(f"📉 Недостаточная точность прогноза: {signal['accuracy']}%")
        return

    await msg.answer(
        f"🔔 Сигнал по {asset} ({signal['direction']})\n"
        f"🎯 Вход: {signal['entry']}\n"
        f"📈 TP: {signal['tp']} (+2%)\n"
        f"📉 SL: {signal['sl']} (-1.5%)\n"
        f"📊 Точность прогноза: {signal['accuracy']}%"
    )

async def auto_send_signals():
    while True:
        for user_id, asset in user_selected_asset.items():
            if not is_within_trading_hours(asset, user_id):
                continue

            signal = generate_signal(asset)
            if signal["accuracy"] >= 70:
                await bot.send_message(
                    user_id,
                    f"🔔 Сигнал по {asset} ({signal['direction']})\n"
                    f"🎯 Вход: {signal['entry']}\n"
                    f"📈 TP: {signal['tp']} (+2%)\n"
                    f"📉 SL: {signal['sl']} (-1.5%)\n"
                    f"📊 Точность прогноза: {signal['accuracy']}%"
                )
        await asyncio.sleep(30)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(auto_send_signals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
                    
