import asyncio
import logging
import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from binance import AsyncClient as BinanceClient
import aiohttp
import numpy as np

API_TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVEDATA_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ⏱ Расписание: по умолчанию круглосуточно
user_schedule = {}
user_assets = {}
user_mute = {}
user_strategy = {}

default_schedule = {
    'Mon': ('00:00', '23:59'),
    'Tue': ('00:00', '23:59'),
    'Wed': ('00:00', '23:59'),
    'Thu': ('00:00', '23:59'),
    'Fri': ('00:00', '23:59'),
    'Sat': ('00:00', '23:59'),
    'Sun': ('00:00', '23:59')
}

assets = ["BTCUSDT", "XAUUSD", "USTECH100"]
strategies = ["MA + RSI + MACD", "Bollinger + Volume"]

# 📲 Клавиатура
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add(KeyboardButton("🔄 Получить сигнал"))
main_kb.row(
    KeyboardButton("BTCUSD"), KeyboardButton("XAUUSD"), KeyboardButton("USTECH100")
)
main_kb.row(KeyboardButton("🔕 Mute"), KeyboardButton("🔔 Unmute"))
main_kb.row(KeyboardButton("🎯 Стратегия"), KeyboardButton("📅 Статус"))

# 📉 Binance
async def get_price_binance(symbol: str) -> float:
    client = await BinanceClient.create()
    ticker = await client.get_symbol_ticker(symbol=symbol)
    await client.close_connection()
    return float(ticker['price'])

# 📊 TwelveData
async def get_price_twelvedata(symbol: str) -> float:
    symbol_map = {"BTCUSDT": "BTC/USD", "XAUUSD": "XAU/USD", "USTECH100": "NAS100"}
    symbol_td = symbol_map.get(symbol, symbol)
    url = f"https://api.twelvedata.com/price?symbol={symbol_td}&apikey={TWELVEDATA_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            if "price" in data:
                return float(data["price"])
            raise ValueError(f"TwelveData error: {data}")

async def get_average_price(symbol: str) -> float:
    try:
        b = await get_price_binance(symbol)
        t = await get_price_twelvedata(symbol)
        return (b + t) / 2
    except:
        return await get_price_binance(symbol)

async def get_price(symbol: str) -> float:
    if symbol == "USTECH100":
        return await get_price_twelvedata(symbol)
    return await get_average_price(symbol)

# 🎯 Комбинированная стратегия
async def analyze_signal(symbol: str, strategy_name="MA + RSI + MACD") -> dict:
    # Упрощенная логика для примера
    price = await get_price(symbol)
    signal = {
        "direction": "Buy" if price % 2 == 0 else "Sell",
        "accuracy": np.random.uniform(60, 85),
        "entry": round(price, 2),
    }
    tp_percent = 1.5
    sl_percent = 0.8
    signal["tp"] = round(price * (1 + tp_percent / 100 if signal["direction"] == "Buy" else 1 - tp_percent / 100), 2)
    signal["sl"] = round(price * (1 - sl_percent / 100 if signal["direction"] == "Buy" else 1 + sl_percent / 100), 2)
    signal["tp_percent"] = tp_percent
    signal["sl_percent"] = sl_percent
    return signal

# ⏰ Проверка расписания
def is_within_schedule(user_id: int) -> bool:
    now = datetime.datetime.now()
    weekday = now.strftime('%a')
    start, end = user_schedule.get(user_id, default_schedule).get(weekday, ('00:00', '23:59'))
    start_time = datetime.datetime.strptime(start, "%H:%M").time()
    end_time = datetime.datetime.strptime(end, "%H:%M").time()
    return start_time <= now.time() <= end_time

# 📡 Отправка сигнала
async def send_signal(user_id: int, symbol: str, is_manual=False):
    if not is_within_schedule(user_id):
        await bot.send_message(user_id, "⏱ Сейчас не торговое время.")
        return

    strategy = user_strategy.get(user_id, "MA + RSI + MACD")
    signal = await analyze_signal(symbol, strategy)
    accuracy = signal["accuracy"]

    if accuracy < 60:
        await bot.send_message(user_id, f"⚠️ Риск велик, не время торговли (точность: {accuracy:.2f}%)")
        return
        
    if is_manual and accuracy < 65:
        await bot.send_message(user_id, f"❌ Недостаточная точность для ручного сигнала ({accuracy:.2f}%)")
        return

    if not is_manual and accuracy < 70:
        return

    msg = (
        f"📡 <b>AI Trading Signal</b>\n"
        f"🔹 Актив: <b>{symbol}</b>\n"
        f"🎯 Направление: <b>{signal['direction']}</b>\n"
        f"🎯 Вход: <b>{signal['entry']}</b>\n"
        f"📈 TP: {signal['tp_percent']}% → <b>{signal['tp']}</b>\n"
        f"📉 SL: {signal['sl_percent']}% → <b>{signal['sl']}</b>\n"
        f"📊 Точность: <b>{accuracy:.2f}%</b>\n"
        f"📘 Стратегия: {strategy}"
    )
    mute = user_mute.get(user_id, False)
    await bot.send_message(user_id, msg, parse_mode="HTML", disable_notification=mute)

# 📥 Старт
@dp.message(commands=["start"])
async def start_handler(msg: types.Message):
    user_assets[msg.from_user.id] = "BTCUSDT"
    user_schedule[msg.from_user.id] = default_schedule.copy()
    user_strategy[msg.from_user.id] = "MA + RSI + MACD"
    await msg.answer("🧠 Пора выбраться из матрицы.", reply_markup=main_kb)

# 📲 Обработка кнопок
@dp.message()
async def handle_message(msg: types.Message):
    user_id = msg.from_user.id
    text = msg.text.strip()

    if text == "🔄 Получить сигнал":
        asset = user_assets.get(user_id, "BTCUSDT")
        await send_signal(user_id, asset, is_manual=True)

    elif text in ["BTCUSD", "XAUUSD", "USTECH100"]:
        mapping = {"BTCUSD": "BTCUSDT", "XAUUSD": "XAUUSD", "USTECH100": "USTECH100"}
        user_assets[user_id] = mapping[text]
        await msg.answer(f"✅ Актив установлен: {text}")

    elif text == "🔕 Mute":
        user_mute[user_id] = True
        await msg.answer("🔕 Уведомления отключены")

    elif text == "🔔 Unmute":
        user_mute[user_id] = False
        await msg.answer("🔔 Уведомления включены")

    elif text == "🎯 Стратегия":
        current = user_strategy.get(user_id, strategies[0])
        idx = strategies.index(current)
        next_strategy = strategies[(idx + 1) % len(strategies)]
        user_strategy[user_id] = next_strategy
        await msg.answer(f"🎯 Стратегия выбрана: {next_strategy}")

    elif text == "📅 Статус":
        sched = user_schedule.get(user_id, default_schedule)
        lines = [f"{day}: {start} - {end}" for day, (start, end) in sched.items()]
        await msg.answer("🗓 <b>Торговое расписание:</b>\n" + "\n".join(lines), parse_mode="HTML")

# 🔁 Автосигналы каждые 30 сек
async def auto_signal_loop():
    while True:
        for user_id, asset in user_assets.items():
            await send_signal(user_id, asset, is_manual=False)
        await asyncio.sleep(30)

# 🚀 Запуск
async def main():
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
