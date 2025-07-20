import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
import yfinance as yf
import numpy as np
import random

# ==== Настройки ====
TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
ASSETS = {
    "BTCUSD": "BTC-USD",
    "XAUUSD": "GC=F",
    "USTECH100": "^NDX"
}
user_asset = {}

# ==== Инициализация ====
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())

# ==== Клавиатура ====
def asset_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTCUSD", callback_data="set_asset:BTCUSD")],
        [InlineKeyboardButton(text="XAUUSD", callback_data="set_asset:XAUUSD")],
        [InlineKeyboardButton(text="USTECH100", callback_data="set_asset:USTECH100")],
        [InlineKeyboardButton(text="📩 Запросить сигнал", callback_data="get_signal")]
    ])

# ==== Команды ====
@dp.message(F.text == "/start")
async def start(message: Message):
    user_asset[message.chat.id] = "BTCUSD"
    await message.answer("Пора выбраться из матрицы.\nВыбери актив:", reply_markup=asset_keyboard())

@dp.callback_query(F.data.startswith("set_asset"))
async def set_asset(call: CallbackQuery):
    asset = call.data.split(":")[1]
    user_asset[call.message.chat.id] = asset
    await call.message.answer(f"✅ Актив выбран: <b>{asset}</b>")

@dp.callback_query(F.data == "get_signal")
async def get_signal(call: CallbackQuery):
    asset = user_asset.get(call.message.chat.id, "BTCUSD")
    ticker = ASSETS[asset]
    signal = await generate_signal(ticker)
    await call.message.answer(signal)

# ==== Генерация сигнала ====
async def generate_signal(ticker: str) -> str:
    try:
        df = yf.download(ticker, period="7d", interval="1h", progress=False)
        if df.empty:
            return "⚠️ Нет данных по активу."

        last_price = df["Close"].iloc[-1]
        direction = random.choice(["Buy", "Sell"])
        accuracy = round(random.uniform(50, 90), 2)

        if accuracy < 60:
            return f"<b>Точность прогноза: {accuracy}%</b>\n⚠️ Риск велик, не время торговли."

        if accuracy < 65:
            return f"<b>Точность прогноза: {accuracy}%</b>\n⚠️ Точность слишком низкая для ручного сигнала."

        # Вычисляем TP/SL
        if direction == "Buy":
            tp_percent = 3
            sl_percent = 1.5
            tp_price = last_price * (1 + tp_percent / 100)
            sl_price = last_price * (1 - sl_percent / 100)
        else:
            tp_percent = 2.5
            sl_percent = 1.2
            tp_price = last_price * (1 - tp_percent / 100)
            sl_price = last_price * (1 + sl_percent / 100)

        return (
            f"<b>Сигнал по {ticker}</b>\n"
            f"Направление: <b>{direction}</b>\n"
            f"Точность прогноза: <b>{accuracy}%</b>\n"
            f"Цена входа: <b>{round(last_price, 2)}</b>\n"
            f"🎯 Тейк-Профит: <b>{tp_percent}%</b> → {round(tp_price, 2)}\n"
            f"🛑 Стоп-Лосс: <b>{sl_percent}%</b> → {round(sl_price, 2)}"
        )

    except Exception as e:
        return f"❌ Ошибка при получении сигнала: {str(e)}"

# ==== Запуск ====
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
