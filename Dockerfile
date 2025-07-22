FROM python:3.10-slim

WORKDIR /app

# Установим зависимости и инструменты
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    gcc \
    make \
    python3-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Скачиваем и собираем TA-Lib
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && ./configure --prefix=/usr && make && make install && \
    cd .. && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Установка Python-зависимостей
COPY requirements.txt .

# Устанавливаем wheel и cython перед ta-lib
RUN pip install --upgrade pip
RUN pip install wheel cython setuptools
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
