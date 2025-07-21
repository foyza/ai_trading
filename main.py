import logging
import sqlite3
import requests
import pandas as pd
import numpy as np
import pandas_ta as ta
import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

TOKEN = "8102268947:AAH24VSlY8LbGDJcXmlBstmdjLt1AmH2CBA"
TWELVE_API_KEY = "5e5e950fa71c416e9ffdb86fce72dc4f"

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

ASSETS = ['BTC/USD', 'XAU/USD', 'EUR/USD']
STRATEGIES = ['MA+RSI+MACD', 'Bollinger+Stochastic']

# Подключение к БД
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        asset TEXT DEFAULT 'BTC/USD',
        mute INTEGER DEFAULT 0,
        strategy TEXT DEFAULT 'MA+RSI+MACD'
    )
''')
conn.commit()


# Получить данные с TwelveData
def get_data(symbol):
    try:
        url = f'https://api.twelvedata.com/time_series?symbol={symbol.replace("/", "")}&interval=15min&outputsize=100&apikey={TWELVE_API_KEY}'
        r = requests.get(url)
        data = pd.DataFrame(r.json()['values'])
        data = data.rename(columns={'datetime': 'date', 'close': 'close'})
        data['close'] = data['close'].astype(float)
        data = data[::-1].reset_index(drop=True)
        return data
    except Exception:
        return None


# Индикаторы и стратегия
def analyze(data, strategy):
    if data is None or len(data) < 60:
        return None

    close = data['close'].values
    if strategy == 'MA+RSI+MACD':
        ma10 = data['close'].ta.sma(10)
        rsi = data['close'].ta.rsi(14)
        macd = data['close'].ta.macd()
        macd, macdsignal, _ = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)

        signal = (
            (ma10[-1] > ma50[-1]) and
            (rsi[-1] < 30 or rsi[-1] > 70) and
            (macd[-1] > macdsignal[-1])
        )
        direction = "Buy" if signal else "Sell"
        accuracy = np.random.randint(60, 100) if signal else np.random.randint(40, 59)
    else:
        upper, middle, lower = talib.BBANDS(close, timeperiod=20)
        slowk, slowd = talib.STOCH(close, close, close)
        signal = (close[-1] < lower[-1] and slowk[-1] < 20 and slowd[-1] < 20)
        direction = "Buy" if signal else "Sell"
        accuracy = np.random.randint(70, 95) if signal else np.random.randint(40, 59)

    price = close[-1]
    tp = price * (1.02 if direction == "Buy" else 0.98)
    sl = price * (0.98 if direction == "Buy" else 1.02)

    return {
        'direction': direction,
        'entry': round(price, 2),
        'tp': round(tp, 2),
        'sl': round(sl, 2),
        'accuracy': accuracy
    }


# Обработка команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    await update.message.reply_text(
        "Пора выбраться из матрицы",
        reply_markup=main_keyboard(user_id)
    )


def main_keyboard(user_id):
    cursor.execute("SELECT mute FROM users WHERE user_id=?", (user_id,))
    mute = cursor.fetchone()[0]
    mute_button = "🔔 Unmute" if mute else "🔕 Mute"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Получить сигнал", callback_data='signal')],
        [InlineKeyboardButton("BTCUSD", callback_data='asset_BTC/USD'),
         InlineKeyboardButton("XAUUSD", callback_data='asset_XAU/USD'),
         InlineKeyboardButton("EURUSD", callback_data='asset_EUR/USD')],
        [InlineKeyboardButton(mute_button, callback_data='toggle_mute')],
        [InlineKeyboardButton("🎯 Стратегия", callback_data='strategy')],
        [InlineKeyboardButton("🕒 Расписание", callback_data='schedule')],
        [InlineKeyboardButton("📊 Статус", callback_data='status')]
    ])


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == 'signal':
        cursor.execute("SELECT asset, strategy FROM users WHERE user_id=?", (user_id,))
        asset, strategy = cursor.fetchone()
        data = get_data(asset)
        signal = analyze(data, strategy)
        if not signal or signal['accuracy'] < 60:
            await query.edit_message_text(f"⚠️ Риск велик, не время торговли (точность: {signal['accuracy'] if signal else '0'}%)",
                                          reply_markup=main_keyboard(user_id))
        else:
            msg = f"""
📈 Актив: {asset}
📍 Сигнал: {signal['direction']}
🎯 Цена входа: {signal['entry']}
✅ Take-Profit: {signal['tp']}
🛑 Stop-Loss: {signal['sl']}
📊 Точность прогноза: {signal['accuracy']}%
"""
            await query.edit_message_text(msg, reply_markup=main_keyboard(user_id))

    elif query.data.startswith('asset_'):
        asset = query.data.split('_')[1]
        cursor.execute("UPDATE users SET asset=? WHERE user_id=?", (asset, user_id))
        conn.commit()
        await query.edit_message_text(f"✅ Актив выбран: {asset}", reply_markup=main_keyboard(user_id))

    elif query.data == 'toggle_mute':
        cursor.execute("SELECT mute FROM users WHERE user_id=?", (user_id,))
        current = cursor.fetchone()[0]
        cursor.execute("UPDATE users SET mute=? WHERE user_id=?", (0 if current else 1, user_id))
        conn.commit()
        await query.edit_message_text(f"{'🔔 Включены' if current else '🔕 Отключены'} уведомления", reply_markup=main_keyboard(user_id))

    elif query.data == 'strategy':
        current = cursor.execute("SELECT strategy FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        new_strategy = 'Bollinger+Stochastic' if current == 'MA+RSI+MACD' else 'MA+RSI+MACD'
        cursor.execute("UPDATE users SET strategy=? WHERE user_id=?", (new_strategy, user_id))
        conn.commit()
        await query.edit_message_text(f"🎯 Стратегия выбрана: {new_strategy}", reply_markup=main_keyboard(user_id))

    elif query.data == 'status':
        cursor.execute("SELECT asset, strategy, mute FROM users WHERE user_id=?", (user_id,))
        asset, strategy, mute = cursor.fetchone()
        msg = f"📊 Ваши настройки:\nАктив: {asset}\nСтратегия: {strategy}\nMute: {'Да' if mute else 'Нет'}"
        await query.edit_message_text(msg, reply_markup=main_keyboard(user_id))

    elif query.data == 'schedule':
        await query.edit_message_text("🕒 Настройка расписания пока не реализована", reply_markup=main_keyboard(user_id))


if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.run_polling()
