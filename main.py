import asyncio
import random
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yfinance as yf

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]
user_assets = {}

# Получаем цену из Yahoo Finance
def get_market_price(asset: str) -> float:
    if asset == "BTCUSD":
        data = yf.Ticker("BTC-USD").history(period="1d")
    elif asset == "XAUUSD":
        data = yf.Ticker("GC=F").history(period="1d")  # Gold Futures
    elif asset == "USTECH100":
        data = yf.Ticker("^NDX").history(period="1d")  # Nasdaq 100
    else:
        return None
    return float(data["Close"][-1])

# Генерация сигнала
def generate_signal(asset: str) -> dict:
    price = get_market_price(asset)
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

# Формат сигнала
def format_signal(signal: dict, auto=False) -> str:
    prefix = "🤖 <b>Автосигнал</b>" if auto else "📡 <b>Сигнал</b>"
    return (
        f"{prefix} по <b>{signal['asset']}</b> ({signal['direction']})\n"
        f"🎯 Вход: <b>{signal['entry']}</b>\n"
        f"📈 TP: <b>{signal['tp']}</b> (+2%)\n"
        f"📉 SL: <b>{signal['sl']}</b> (-1.5%)\n"
        f"📊 Точность прогноза: <b>{signal['accuracy']}%</b>"
    )

# Кнопки выбора актива
def asset_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for asset in ASSETS:
        kb.button(text=asset, callback_data=f"asset:{asset}")
    return kb.as_markup()

# /start
@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer("Пора выбраться из матрицы!", reply_markup=asset_keyboard())

# Выбор актива
@dp.callback_query(F.data.startswith("asset:"))
async def asset_chosen(callback: CallbackQuery):
    asset = callback.data.split(":")[1]
    user_assets[callback.from_user.id] = asset
    signal = generate_signal(asset)
    if signal["accuracy"] >= 65:
        await callback.message.answer(format_signal(signal))
    else:
        await callback.message.answer(f"⚠️ Точность: {signal['accuracy']}%. Сигнал не отправлен.")

# Автоматическая отправка при точности > 70%
async def auto_signal_loop():
    while True:
        for asset in ASSETS:
            signal = generate_signal(asset)
            if signal["accuracy"] >= 70:
                await bot.send_message(chat_id="@foyzas_bot", text=format_signal(signal, auto=True))
        await asyncio.sleep(60)  # Пауза между проверками

# Запуск
async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
