import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]


def generate_prediction(asset: str):
    # Здесь стоит подключать ML-модель или API
    current_price = random.uniform(1000, 60000)
    direction = random.choice(["Buy", "Sell"])
    accuracy = round(random.uniform(60, 95), 2)

    if direction == "Buy":
        tp = current_price * 1.02  # +2%
        sl = current_price * 0.985  # -1.5%
    else:
        tp = current_price * 0.98  # -2%
        sl = current_price * 1.015  # +1.5%

    return {
        "asset": asset,
        "price": round(current_price, 2),
        "direction": direction,
        "tp": round(tp, 2),
        "sl": round(sl, 2),
        "accuracy": accuracy
    }


@dp.message(Command("start"))
async def start_handler(msg: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Получить сигнал", callback_data="get_signal")],
        [InlineKeyboardButton(text="📉 Выбрать актив", callback_data="choose_asset")]
    ])
    await msg.answer("👋 Добро пожаловать в AI Trading Bot!\nВыберите действие:", reply_markup=keyboard)


@dp.callback_query(F.data == "choose_asset")
async def choose_asset(callback_query):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=asset, callback_data=f"asset_{asset}")]
            for asset in ASSETS
        ]
    )
    await callback_query.message.answer("💱 Выберите актив:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("asset_"))
async def asset_selected(callback_query):
    asset = callback_query.data.split("_")[1]
    prediction = generate_prediction(asset)

    if prediction["accuracy"] < 65:
        await callback_query.message.answer(
            f"📉 Точность прогноза по {asset} слишком низкая: {prediction['accuracy']}%.\nПовторите позже."
        )
        return

    text = (
        f"🔔 Сигнал по {asset} ({prediction['direction']})\n"
        f"🎯 Вход: {prediction['price']}\n"
        f"📈 TP: {prediction['tp']} (+2%)\n"
        f"📉 SL: {prediction['sl']} (-1.5%)\n"
        f"📊 Точность прогноза: {prediction['accuracy']}%"
    )
    await callback_query.message.answer(text)


@dp.callback_query(F.data == "get_signal")
async def manual_signal(callback_query):
    # Выбираем случайный актив
    asset = random.choice(ASSETS)
    prediction = generate_prediction(asset)

    if prediction["accuracy"] < 65:
        await callback_query.message.answer(
            f"📉 Точность прогноза по {asset} слишком низкая: {prediction['accuracy']}%.\nПовторите позже."
        )
        return

    text = (
        f"🔔 Сигнал по {asset} ({prediction['direction']})\n"
        f"🎯 Вход: {prediction['price']}\n"
        f"📈 TP: {prediction['tp']} (+2%)\n"
        f"📉 SL: {prediction['sl']} (-1.5%)\n"
        f"📊 Точность прогноза: {prediction['accuracy']}%"
    )
    await callback_query.message.answer(text)


async def auto_send_signals():
    while True:
        for asset in ASSETS:
            prediction = generate_prediction(asset)
            if prediction["accuracy"] >= 70:
                text = (
                    f"🔔 <b>Автосигнал</b> по {asset} ({prediction['direction']})\n"
                    f"🎯 Вход: {prediction['price']}\n"
                    f"📈 TP: {prediction['tp']} (+2%)\n"
                    f"📉 SL: {prediction['sl']} (-1.5%)\n"
                    f"📊 Точность прогноза: {prediction['accuracy']}%"
                )
                
                await bot.send_message(chat_id="813631865", text=text)
        await asyncio.sleep(60)  # Проверка каждую минуту


async def main():
    asyncio.create_task(auto_send_signals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
