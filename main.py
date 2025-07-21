import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from binance import AsyncClient
import aiohttp
import numpy as np

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TD_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"

bot = Bot(token=TOKEN)
dp = Dispatcher()

ASSETS = ["BTCUSD", "XAUUSD", "USTECH100"]
user_settings = {}

def get_keyboard():
    buttons = [
        [KeyboardButton(text="🔄 Получить сигнал")],
        [KeyboardButton(text="BTCUSD"), KeyboardButton(text="XAUUSD"), KeyboardButton(text="USTECH100")],
        [KeyboardButton(text="🔕 Mute"), KeyboardButton(text="🔔 Unmute")],
        [KeyboardButton(text="🎯 Стратегия: MA+RSI+MACD"), KeyboardButton(text="🎯 Стратегия: BB+Vol")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Инициализация Binance клиента
binance_client = None

async def fetch_binance_price(symbol):
    try:
        res = await binance_client.get_klines(symbol=symbol, interval='5m', limit=50)
        return [{'close': float(i[4])} for i in res]
    except:
        return None

async def fetch_twelvedata_price(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&apikey={TD_API_KEY}&outputsize=50"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            data = await r.json()
            if "values" in data:
                return [{'close': float(i['close'])} for i in reversed(data['values'])]
            return None

async def fetch_ohlcv(asset):
    if asset == "BTCUSD":
        binance = await fetch_binance_price("BTCUSDT")
        twelve = await fetch_twelvedata_price("BTC/USD")
    elif asset == "XAUUSD":
        binance = await fetch_binance_price("XAUUSDT")
        twelve = await fetch_twelvedata_price("XAU/USD")
    elif asset == "USTECH100":
        return await fetch_twelvedata_price("NAS100")
    else:
        return None

    if not binance or not twelve:
        return binance or twelve

    return [{'close': (b['close'] + t['close']) / 2} for b, t in zip(binance, twelve)]

def rsi(values, period=14):
    deltas = np.diff(values)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = 100. - 100. / (1. + rs)
    return rsi

def macd(values):
    exp1 = np.mean(values[-12:])
    exp2 = np.mean(values[-26:])
    return exp1 - exp2

def bbands(values):
    ma = np.mean(values[-20:])
    std = np.std(values[-20:])
    upper = ma + 2 * std
    lower = ma - 2 * std
    return upper, lower

def generate_signal(candles, strategy="MA+RSI+MACD"):
    closes = [c['close'] for c in candles]
    ma10 = np.mean(closes[-10:])
    ma50 = np.mean(closes[-50:])
    rsi_val = rsi(closes)
    macd_val = macd(closes)
    price = closes[-1]

    indicators_agree = 0
    direction = None

    if strategy == "MA+RSI+MACD":
        if ma10 > ma50:
            indicators_agree += 1
            direction = "buy"
        elif ma10 < ma50:
            indicators_agree += 1
            direction = "sell"
        if rsi_val < 30:
            indicators_agree += 1
            direction = "buy"
        elif rsi_val > 70:
            indicators_agree += 1
            direction = "sell"
        if macd_val > 0:
            indicators_agree += 1
            direction = "buy"
        elif macd_val < 0:
            indicators_agree += 1
            direction = "sell"
    else:
        upper, lower = bbands(closes)
        vol = abs(closes[-1] - closes[-2])
        if price > upper:
            indicators_agree += 1
            direction = "sell"
        elif price < lower:
            indicators_agree += 1
            direction = "buy"
        if vol > np.mean(np.diff(closes)):
            indicators_agree += 1

    accuracy = int((indicators_agree / 3) * 100)
    if indicators_agree >= 3:
        return True, direction, accuracy
    elif indicators_agree == 2:
        return False, direction, accuracy
    else:
        return False, None, accuracy

def get_user_setting(user_id, key, default):
    return user_settings.get(user_id, {}).get(key, default)

def set_user_setting(user_id, key, value):
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id][key] = value

async def send_signal(user_id, asset, silent=False, manual=False):
    candles = await fetch_ohlcv(asset)
    if not candles:
        await bot.send_message(user_id, "❌ Ошибка при получении данных.")
        return

    strategy = get_user_setting(user_id, "strategy", "MA+RSI+MACD")
    signal, direction, accuracy = generate_signal(candles, strategy)

    if accuracy < 60:
        await bot.send_message(user_id, f"⚠️ Риск велик, не время торговли (точность: {accuracy}%)")
        return
    if manual and accuracy < 65:
        await bot.send_message(user_id, f"⚠️ Недостаточная точность для ручного сигнала (точность: {accuracy}%)")
        return
    if not manual and accuracy < 70:
        return

    price = candles[-1]['close']
    tp_pct = 2.0 * (accuracy / 100)
    sl_pct = 1.0 * (accuracy / 100)

    tp_price = round(price * (1 + tp_pct / 100), 2) if direction == "buy" else round(price * (1 - tp_pct / 100), 2)
    sl_price = round(price * (1 - sl_pct / 100), 2) if direction == "buy" else round(price * (1 + sl_pct / 100), 2)

    msg = (
        f"📈 Сигнал: {direction.upper()}\n"
        f"🎯 Вход: {price}\n"
        f"🟢 TP: +{round(tp_pct, 2)}% → {tp_price}\n"
        f"🔴 SL: -{round(sl_pct, 2)}% → {sl_price}\n"
        f"📊 Точность: {accuracy}%"
    )
    await bot.send_message(user_id, msg, disable_notification=silent)

@dp.message(F.text == "/start")
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    set_user_setting(user_id, "asset", "BTCUSD")
    set_user_setting(user_id, "silent", False)
    set_user_setting(user_id, "strategy", "MA+RSI+MACD")
    await message.answer("Пора выбраться из матрицы.", reply_markup=get_keyboard())

@dp.message(F.text == "🔄 Получить сигнал")
async def handle_get_signal(message: types.Message):
    user_id = message.from_user.id
    asset = get_user_setting(user_id, "asset", "BTCUSD")
    await send_signal(user_id, asset, manual=True)

@dp.message(F.text.in_(ASSETS))
async def handle_asset(message: types.Message):
    user_id = message.from_user.id
    set_user_setting(user_id, "asset", message.text)
    await message.answer(f"Актив переключен на {message.text}")

@dp.message(F.text == "🔕 Mute")
async def mute_handler(message: types.Message):
    set_user_setting(message.from_user.id, "silent", True)
    await message.answer("🔕 Сигналы теперь без звука.")

@dp.message(F.text == "🔔 Unmute")
async def unmute_handler(message: types.Message):
    set_user_setting(message.from_user.id, "silent", False)
    await message.answer("🔔 Сигналы теперь со звуком.")

@dp.message(F.text.startswith("🎯 Стратегия"))
async def handle_strategy(message: types.Message):
    user_id = message.from_user.id
    if "BB+Vol" in message.text:
        set_user_setting(user_id, "strategy", "BB+Vol")
        await message.answer("Стратегия переключена на 🎯 Bollinger Bands + Volume")
    else:
        set_user_setting(user_id, "strategy", "MA+RSI+MACD")
        await message.answer("Стратегия переключена на 🎯 MA + RSI + MACD")

async def scheduler():
    while True:
        for user_id in user_settings:
            asset = get_user_setting(user_id, "asset", "BTCUSD")
            silent = get_user_setting(user_id, "silent", False)
            await send_signal(user_id, asset, silent=silent)
        await asyncio.sleep(60)

async def main():
    global binance_client
    binance_client = await AsyncClient.create()
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
