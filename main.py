import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import datetime
from core import generate_signal

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())

user_settings = {}

class Settings(StatesGroup):
    waiting_for_day = State()
    waiting_for_hour = State()

def get_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📈 Запросить сигнал", callback_data="get_signal")
    kb.button(text="⚙️ Изменить актив", callback_data="change_asset")
    kb.button(text="🕰 Изменить время", callback_data="change_schedule")
    kb.adjust(1)
    return kb.as_markup()

@dp.message(F.text, commands="start")
async def start(message: types.Message):
    user_id = message.from_user.id
    user_settings[user_id] = {"asset": "BTC-USD", "schedule": {"days": list(range(7)), "hours": list(range(24))}}
    await message.answer("Пора выбраться из матрицы", reply_markup=get_keyboard())

@dp.callback_query(F.data == "change_asset")
async def change_asset(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTCUSD", callback_data="asset_BTC-USD")],
        [InlineKeyboardButton(text="XAUUSD", callback_data="asset_GC=F")],
        [InlineKeyboardButton(text="USTECH100", callback_data="asset_NDX")]
    ])
    await callback.message.edit_text("Выбери актив:", reply_markup=kb)

@dp.callback_query(F.data.startswith("asset_"))
async def set_asset(callback: types.CallbackQuery):
    asset = callback.data.split("_")[1]
    user_settings[callback.from_user.id]["asset"] = asset
    await callback.message.edit_text(f"Акттив установлен: <b>{asset}</b>", reply_markup=get_keyboard())

@dp.callback_query(F.data == "change_schedule")
async def ask_day(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи дни недели (0-пн ... 6-вс) через запятую:")
    await state.set_state(Settings.waiting_for_day)

@dp.message(Settings.waiting_for_day)
async def set_days(message: types.Message, state: FSMContext):
    try:
        days = list(map(int, message.text.split(",")))
        await state.update_data(days=days)
        await message.answer("Теперь введи часы (например: 9,12,18):")
        await state.set_state(Settings.waiting_for_hour)
    except:
        await message.answer("Неверный формат. Попробуй снова.")

@dp.message(Settings.waiting_for_hour)
async def set_hours(message: types.Message, state: FSMContext):
    try:
        hours = list(map(int, message.text.split(",")))
        data = await state.get_data()
        user_settings[message.from_user.id]["schedule"] = {
            "days": data["days"],
            "hours": hours
        }
        await message.answer("Расписание обновлено", reply_markup=get_keyboard())
        await state.clear()
    except:
        await message.answer("Ошибка. Попробуй снова.")

@dp.callback_query(F.data == "get_signal")
async def get_signal_now(callback: types.CallbackQuery):
    asset = user_settings[callback.from_user.id]["asset"]
    signal = generate_signal(asset)
    if signal:
        if signal["accuracy"] < 60:
            await callback.message.answer(f'Точность: <b>{signal["accuracy"]}%</b>\n⚠️ Риск велик, не время торговли')
        elif signal["accuracy"] >= 65:
            await callback.message.answer(signal["message"], reply_markup=get_keyboard())
    else:
        await callback.message.answer("Нет данных.")

async def auto_send_signals():
    while True:
        now = datetime.datetime.now()
        for user_id, settings in user_settings.items():
            if now.weekday() in settings["schedule"]["days"] and now.hour in settings["schedule"]["hours"]:
                asset = settings["asset"]
                signal = generate_signal(asset)
                if signal and signal["accuracy"] >= 70:
                    try:
                        await bot.send_message(chat_id=user_id, text=signal["message"], reply_markup=get_keyboard())
                    except Exception as e:
                        print(f"Ошибка при отправке {e}")
        await asyncio.sleep(300)

async def main():
    asyncio.create_task(auto_send_signals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
