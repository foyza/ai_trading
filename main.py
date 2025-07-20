import asyncio
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging

API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

TRADABLE_ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]
user_trading_hours = {}

@dp.message(CommandStart())
async def start_cmd(msg: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Получить сигнал", callback_data="get_signal")
    kb.button(text="⏰ Задать часы", callback_data="set_hours")
    kb.button(text="💱 Активы", callback_data="select_asset")
    await msg.answer("Пора выбереться из матрицы!", reply_markup=kb.as_markup())

@dp.callback_query()
async def handle_callback(call: types.CallbackQuery):
    if call.data == "get_signal":
        await send_signal(call.message, call.from_user.id)
    elif call.data == "set_hours":
        await call.message.answer("Формат: /sethours ASSET START END")
    elif call.data == "select_asset":
        await call.message.answer("Выбери актив: BTCUSD, XAUUSD, USTECH100")

@dp.message(Command("sethours"))
async def set_hours_cmd(msg: types.Message):
    parts = msg.text.split()
    if len(parts) != 4:
        await msg.answer("Используй формат: /sethours BTCUSD 9 18")
        return
    asset, start, end = parts[1], int(parts[2]), int(parts[3])
    if asset not in TRADABLE_ASSETS:
        await msg.answer("⛔️ Актив недопустим.")
        return
    user_id = msg.from_user.id
    if user_id not in user_trading_hours:
        user_trading_hours[user_id] = {}
    user_trading_hours[user_id][asset] = {"hours": (start, end)}
    await msg.answer(f"✅ Время для {asset} установлено: {start}:00 - {end}:00")

def is_trading_hour(user_id, asset):
    from datetime import datetime
    now = datetime.now().hour
    hours = user_trading_hours.get(user_id, {}).get(asset, {}).get("hours")
    return not hours or hours[0] <= now < hours[1]

def generate_signal():
    signal = random.choice(["Buy", "Sell"])
    entry = random.uniform(100, 50000)
    tp = round(entry * 1.02, 2)
    sl = round(entry * 0.985, 2)
    acc = round(random.uniform(60, 90), 2)
    return signal, entry, tp, sl, acc

async def send_signal(msg, user_id, auto=False):
    asset = "BTCUSD"
    if not is_trading_hour(user_id, asset):
        await msg.answer("⛔️ Сейчас не ваше торговое время.")
        return
    signal, entry, tp, sl, acc = generate_signal()
    if auto and acc < 70:
        return
    if not auto and acc < 65:
        await msg.answer(f"❌ Нет сигнала (точность {acc}%)")
        return
    text = f"🔔 Сигнал по {asset} ({signal})\n🎯 Вход: {entry:.2f}\n📈 TP: {tp:.2f} (+2%)\n📉 SL: {sl:.2f} (-1.5%)\n📊 Точность прогноза: {acc}%"
    await msg.answer(text)

async def auto_signal_sender():
    while True:
        await asyncio.sleep(60)
        for user_id in user_trading_hours:
            dummy = types.Message(message_id=0, chat=types.Chat(id=user_id, type='private'), date=None, text="")
            try:
                await send_signal(dummy, user_id, auto=True)
            except Exception as e:
                logging.warning(f"Ошибка автоотправки {user_id}: {e}")

async def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.create_task(auto_signal_sender())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
