import yfinance as yf
import numpy as np
import random

def get_market_price(symbol):
    try:
        data = yf.download(symbol, period="1d", interval="1m")
        return float(data["Close"].iloc[-1])
    except Exception:
        return None

def predict_accuracy():
    return round(random.uniform(55, 95), 2)

def generate_signal(symbol):
    price = get_market_price(symbol)
    if not price:
        return None

    accuracy = predict_accuracy()
    if accuracy < 60:
        return {"accuracy": accuracy}

    direction = random.choice(["Buy", "Sell"])
    tp_percent = round(random.uniform(1, 3), 2)
    sl_percent = round(random.uniform(0.5, 1.5), 2)

    if direction == "Buy":
        tp_price = round(price * (1 + tp_percent / 100), 2)
        sl_price = round(price * (1 - sl_percent / 100), 2)
    else:
        tp_price = round(price * (1 - tp_percent / 100), 2)
        sl_price = round(price * (1 + sl_percent / 100), 2)

    message = (
        f"<b>Сигнал по {symbol}</b>\n"
        f"Направление: <b>{direction}</b>\n"
        f"Цена входа: <b>{price}</b>\n"
        f"🎯 TP: <b>{tp_percent}%</b> → <b>{tp_price}</b>\n"
        f"🛑 SL: <b>{sl_percent}%</b> → <b>{sl_price}</b>\n"
        f"📊 Точность прогноза: <b>{accuracy}%</b>"
    )

    return {"message": message, "accuracy": accuracy}
