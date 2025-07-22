FROM python:3.10-slim

WORKDIR /app

# Устанавливаем system-зависимости + TA-Lib
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libta-lib0 \
    ta-lib \
    python3-dev \
    && apt-get clean

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
