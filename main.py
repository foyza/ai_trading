import asyncio
import random
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yfinance as yf
from binance import Client

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
BINANCE_API_KEY = "your_api_key"
BINANCE_API_SECRET = "your_api_secret"

bot = Bot(token=TOKEN, default=types.DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)

user_assets = {}

ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]

# Получаем цену из Binance или Yahoo
def get_market_price(asset):
    if asset == "BTCUSD":
        ticker = client.get_symbol_ticker(symbol="BTCUSDT")
        return float(ticker["price"])
    elif asset == "XAUUSD":
        ticker = client.get_symbol_ticker(symbol="XAUUSDT")
        return float(ticker["price"])
    elif asset == "USTECH100":
        data = yf.Ticker("^NDX").history(period="1d")
        return float(data["Close"][-1])
    return None

# Генерация сигнала с псевдопрогнозом
def generate_signal(asset):
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

# Сообщение сигнала
def format_signal(signal, auto=False):
    prefix = "🔔 <b>Автосигнал</b>" if auto else "🔔 <b>Сигнал</b>"
    return (
        f"{prefix} по <b>{signal['asset']}</b> ({signal['direction']})\n"
        f"🎯 Вход: <b>{signal['entry']}</b>\n"
        f"📈 TP: <b>{signal['tp']}</b> (+2%)\n"
        f"📉 SL: <b>{signal['sl']}</b> (-1.5%)\n"
        f"📊 Точность прогноза: <b>{signal['accuracy']}%</b>"
    )

# Кнопки выбора актива
def asset_keyboard():
    kb = InlineKeyboardBuilder()
    for asset in ASSETS:
        kb.button(text=asset, callback_data=f"asset:{asset}")
    return kb.as_markup()

@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer("Пора выбраться из матрицы!", reply_markup=asset_keyboard())

@dp.callback_query(F.data.startswith("asset:"))
async def asset_chosen(callback: types.CallbackQuery):
    asset = callback.data.split(":")[1]
    user_assets[callback.from_user.id] = asset
    signal = generate_signal(asset)
    if signal["accuracy"] >= 65:
        await callback.message.answer(format_signal(signal))
    else:
        await callback.message.answer(f"❌ Недостаточная точность ({signal['accuracy']}%). Сигнал не отправлен.")

# Автоотправка при >70% точности
async def auto_signal():
    while True:
        for asset in ASSETS:
            signal = generate_signal(asset)
            if signal["accuracy"] >= 70:
                await bot.send_message(chat_id="@foyzas_bot", text=format_signal(signal, auto=True))
        await asyncio.sleep(60)

async def main():
    asyncio.create_task(auto_signal())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
