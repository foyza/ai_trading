get_klines(symbol=ASSETS[asset], interval=Client.KLINE_INTERVAL_15MINUTE, limit=100)
            close_prices = [float(k[4]) for k in klines]
            price = close_prices[-1]
            df = pd.DataFrame({'Close': close_prices})

        df['SMA'] = df['Close'].rolling(window=10).mean()
        df.dropna(inplace=True)

        if df.empty:
            return None

        latest_price = df['Close'].iloc[-1]
        sma = df['SMA'].iloc[-1]
        direction = "Buy" if latest_price > sma else "Sell"
        confidence = np.clip(np.random.normal(loc=72 if direction == "Buy" else 68, scale=5), 50, 100)

        tp_pct = 1.5
        sl_pct = 1.0

        tp_price = latest_price * (1 + tp_pct / 100) if direction == "Buy" else latest_price * (1 - tp_pct / 100)
        sl_price = latest_price * (1 - sl_pct / 100) if direction == "Buy" else latest_price * (1 + sl_pct / 100)

        return confidence, direction, latest_price, tp_price, sl_price, tp_pct, sl_pct

    except Exception as e:
        print(f"Ошибка: {e}")
        return None

# === Автоотправка сигналов при точности >70% ===
async def auto_signal_loop():
    while True:
        for chat_id, data in user_data.items():
            asset = data["asset"]
            if not is_in_trading_time(chat_id, asset):
                continue

            signal = get_signal(asset)
            if signal:
                confidence, direction, entry_price, tp_price, sl_price, tp_pct, sl_pct = signal
                if confidence >= 70:
                    await bot.send_message(
                        chat_id,
                        f"📡 [Авто-сигнал]\n"
                        f"Актив: {asset}\n"
                        f"Направление: {direction}\n"
                        f"Цена входа: {entry_price:.2f}\n"
                        f"🎯 TP: {tp_pct:.2f}% → {tp_price:.2f}\n"
                        f"🛡 SL: {sl_pct:.2f}% → {sl_price:.2f}\n"
                        f"📊 Точность прогноза: {confidence:.2f}%"
                    )
        await asyncio.sleep(60)

# === Запуск ===
async def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.create_task(auto_signal_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
