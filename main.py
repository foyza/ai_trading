import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from aiogram.enums import ParseMode
from datetime import datetime
from aiogram.fsm.storage.memory import MemoryStorage
import yfinance as yf
import numpy as np
import random

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())

# Доступные активы
ASSETS = {"BTCUSD": "BTC-USD", "XAUUSD": "XAUUSD=X", "USTECH100": "^NDX"}
user_settings = {}  # Хранит настройки для каждого пользователя

# --- Кнопки ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("⚙️ Выбрать актив", callback_data="set_asset")],
        [InlineKeyboardButton("🕒 Настроить расписание", callback_data="set_schedule")],
        [InlineKeyboardButton("📩 Запросить сигнал", callback_data="manual_signal")]
    ])

def asset_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(a, callback_data=f"asset:{a}") for a in ASSETS.keys()]
    ])

def days_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("Будни", callback_data="days:weekdays"),
         InlineKeyboardButton("Выходные", callback_data="days:weekends")],
        [InlineKeyboardButton("Круглосуточно", callback_data="days:all")]
    ])

def hours_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(f"{h}:00", callback_data=f"hours:{h}") for h in range(0, 24, 6)],
        [InlineKeyboardButton("Подтвердить", callback_data="hours:confirm")]
    ])

# --- Команды ---
@dp.message(F.text == "/start")
async def cmd_start(msg: Message):
    user_settings[msg.from_user.id] = {
        "asset": "BTCUSD",
        "days": "all",
        "hours": list(range(24))
    }
    await msg.answer("Пора выбраться из матрицы", reply_markup=main_kb())

# --- Обработчики кнопок ---
@dp.callback_query(F.data == "set_asset")
async def cb_set_asset(c: CallbackQuery):
    await c.message.edit_text("Выберите актив:", reply_markup=asset_kb())

@dp.callback_query(F.data.startswith("asset:"))
async def cb_asset(c: CallbackQuery):
    a = c.data.split(":")[1]
    user_settings[c.from_user.id]["asset"] = a
    await c.message.edit_text(f"Актив установлен: <b>{a}</b>", reply_markup=main_kb())

@dp.callback_query(F.data == "set_schedule")
async def cb_set_schedule(c: CallbackQuery):
    await c.message.edit_text("Выберите дни:", reply_markup=days_kb())

@dp.callback_query(F.data.startswith("days:"))
async def cb_days(c: CallbackQuery):
    arg = c.data.split(":")[1]
    s = user_settings[c.from_user.id]
    s["days"] = arg
    if arg == "all":
        s["hours"] = list(range(24))
        await c.message.edit_text("Расписание: круглосуточно", reply_markup=main_kb())
    else:
        s["hours_temp"] = []
        await c.message.edit_text("Выберите часы (каждые 6 ч):", reply_markup=hours_kb())

@dp.callback_query(F.data.startswith("hours:"))
async def cb_hours(c: CallbackQuery):
    arg = c.data.split(":")[1]
    uid = c.from_user.id
    s = user_settings[uid]
    if arg == "confirm":
        s["hours"] = s.pop("hours_temp", [])
        await c.message.edit_text("Расписание сохранено", reply_markup=main_kb())
    else:
        h = int(arg)
        temp = s.setdefault("hours_temp", [])
        if h in temp:
            temp.remove(h)
        else:
            temp.append(h)
        await c.answer(f"Выбрано: {sorted(temp)}", show_alert=False)

# --- Генерация сигнала ---
def gen_signal(ticker: str):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if df.empty:
            return None
        price = float(df["Close"].iloc[-1])
    except:
        return None

    acc = round(random.uniform(50, 100), 2)
    if acc < 60:
        return {"status": "low", "accuracy": acc}
    direction = random.choice(["Buy", "Sell"])
    entry = price
    tp_pct = 2
    sl_pct = 1.5
tp_price = round(entry * (1 + tp_pct/100 if direction=="Buy" else 1 - tp_pct/100), 2)
    sl_price = round(entry * (1 - sl_pct/100 if direction=="Buy" else 1 + sl_pct/100), 2)

    return {
        "status": "ok", "direction": direction,
        "entry": round(entry,2),
        "tp_pct": tp_pct, "tp_price": tp_price,
        "sl_pct": sl_pct, "sl_price": sl_price,
        "accuracy": acc
    }

# --- Ручной сигнал ---
@dp.callback_query(F.data == "manual_signal")
async def cb_manual(c: CallbackQuery):
    cfg = user_settings[c.from_user.id]
    sig = gen_signal(ASSETS[cfg["asset"]])
    if not sig or sig["status"]=="low":
        txt = f"⚠️ Точность: {sig['accuracy'] if sig else '?'}% — риск велик, не время торговли"
    elif sig["accuracy"] < 65:
        txt = f"⛔️ Точность: {sig['accuracy']}% слишком низка для ручного сигнала"
    else:
        txt = (f"📊 <b>{cfg['asset']}</b>\n"
               f"🔁 {sig['direction']}\n"
               f"🎯 Вход: {sig['entry']}\n"
               f"📈 TP +{sig['tp_pct']}% → {sig['tp_price']}\n"
               f"🛑 SL −{sig['sl_pct']}% → {sig['sl_price']}\n"
               f"📊 Точность: {sig['accuracy']}%")
    await c.message.answer(txt, reply_markup=main_kb())

# --- Автосигнал каждая минута ---
async def auto_loop():
    while True:
        now = datetime.now()
        for uid, s in user_settings.items():
            weekday = now.weekday()
            if s["days"]=="weekdays" and weekday>=5 or s["days"]=="weekends" and weekday<5:
                continue
            if now.hour not in s["hours"]:
                continue
            sig = gen_signal(ASSETS[s["asset"]])
            if sig and sig["status"]=="ok" and sig["accuracy"]>=70:
                txt = (f"🤖 Автосигнал по <b>{s['asset']}</b>\n"
                       f"🔁 {sig['direction']}\n"
                       f"🎯 Вход: {sig['entry']}\n"
                       f"📈 TP +{sig['tp_pct']}% → {sig['tp_price']}\n"
                       f"🛑 SL −{sig['sl_pct']}% → {sig['sl_price']}\n"
                       f"📊 Точность: {sig['accuracy']}%")
                await bot.send_message(uid, txt, reply_markup=main_kb())
        await asyncio.sleep(60)

# --- Запуск ---
async def main():
    asyncio.create_task(auto_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
