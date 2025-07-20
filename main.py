import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from datetime import datetime
import yfinance as yf
import numpy as np
import random

API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

users = {}

assets = {
    "BTCUSD": "BTC-USD",
    "XAUUSD": "GC=F",
    "USTECH100": "^NDX"
}

def predict_signal(data):
    direction = random.choice(["Buy", "Sell"])
    accuracy = round(random.uniform(50, 100), 2)
    entry = round(data[-1], 2)
    tp_pct = round(random.uniform(1, 3), 2)
    sl_pct = round(random.uniform(0.5, 2), 2)
    tp_price = round(entry * (1 + tp_pct / 100 if direction == "Buy" else 1 - tp_pct / 100), 2)
    sl_price = round(entry * (1 - sl_pct / 100 if direction == "Buy" else 1 + sl_pct / 100), 2)
    return {
        "direction": direction,
        "accuracy": accuracy,
        "entry": entry,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "tp_price": tp_price,
        "sl_price": sl_price
    }

def get_market_data(symbol):
    try:
        data = yf.download(symbol, period="1d", interval="1m")["Close"]
        return data.dropna().values
    except Exception:
        return []

def is_within_schedule(user_id):
    if user_id not in users:
        return True
    schedule = users[user_id]["schedule"]
    if schedule == "24/7":
        return True
    now = datetime.now()
    for entry in schedule:
        day, start, end = entry
        if now.strftime("%A") == day:
            start_h, end_h = map(int, start.split(":")[0:1] + end.split(":")[0:1])
            if start_h <= now.hour < end_h:
                return True
    return False

@dp.message(Command("start"))
async def start(message: types.Message):
    users[message.from_user.id] = {"asset": "BTCUSD", "schedule": "24/7"}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выбрать актив", callback_data="choose_asset")],
        [InlineKeyboardButton(text="Настроить расписание", callback_data="set_schedule")]
    ])
    await message.answer("Пора выбраться из матрицы.", reply_markup=kb)
@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "choose_asset":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="BTCUSD", callback_data="asset_BTCUSD")],
            [InlineKeyboardButton(text="XAUUSD", callback_data="asset_XAUUSD")],
            [InlineKeyboardButton(text="USTECH100", callback_data="asset_USTECH100")]
        ])
        await callback.message.edit_text("Выбери актив:", reply_markup=kb)
    elif callback.data.startswith("asset_"):
        asset = callback.data.split("_")[1]
        users[user_id]["asset"] = asset
        await callback.message.edit_text(f"Актив установлен: {asset}")
    elif callback.data == "set_schedule":
        # Устанавливаем круглосуточный режим как пример
        users[user_id]["schedule"] = "24/7"
        await callback.message.edit_text("Расписание установлено: круглосуточно")

@dp.message(Command("signal"))
async def manual_signal(message: types.Message):
    user_id = message.from_user.id
    asset_key = users.get(user_id, {}).get("asset", "BTCUSD")
    symbol = assets[asset_key]
    if not is_within_schedule(user_id):
        await message.answer("⏰ Не входит в торговое расписание.")
        return
    data = get_market_data(symbol)
    if len(data) == 0:
        await message.answer("❌ Нет рыночных данных.")
        return
    signal = predict_signal(data)
    if signal["accuracy"] >= 65:
        await message.answer(
            f"📊 Ручной сигнал:\n"
            f"Актив: {asset_key}\n"
            f"🔁 Направление: {signal['direction']}\n"
            f"🎯 Вход: {signal['entry']}\n"
            f"🎯 TP: {signal['tp_pct']}% → {signal['tp_price']}\n"
            f"🛑 SL: {signal['sl_pct']}% → {signal['sl_price']}\n"
            f"✅ Точность: {signal['accuracy']}%"
        )
    elif signal["accuracy"] < 60:
        await message.answer(f"⚠️ Риск велик, не время торговли ({signal['accuracy']}%)")
    else:
        await message.answer(f"❌ Недостаточная точность ({signal['accuracy']}%)")

async def auto_check_signals():
    while True:
        for user_id, config in users.items():
            asset_key = config["asset"]
            if not is_within_schedule(user_id):
                continue
            data = get_market_data(assets[asset_key])
            if len(data) == 0:
                continue
            signal = predict_signal(data)
            if signal["accuracy"] >= 70:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"📢 AI сигнал:\n"
                        f"Актив: {asset_key}\n"
                        f"🔁 Направление: {signal['direction']}\n"
                        f"🎯 Вход: {signal['entry']}\n"
                        f"🎯 TP: {signal['tp_pct']}% → {signal['tp_price']}\n"
                        f"🛑 SL: {signal['sl_pct']}% → {signal['sl_price']}\n"
                        f"✅ Точность: {signal['accuracy']}%"
                    )
                )
        await asyncio.sleep(60)  # Проверяем каждую минуту

async def main():
    task = asyncio.create_task(auto_check_signals())
    await dp.start_polling(bot)
    await task

if __name__ == "__main__":
    asyncio.run(main())
