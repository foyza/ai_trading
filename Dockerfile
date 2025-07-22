FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    curl \
    gcc \
    make \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Установка библиотеки TA-Lib из исходников
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && ./configure --prefix=/usr && make && make install && \
    cd .. && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Установка Python-зависимостей
COPY requirements.txt .

RUN pip install --upgrade pip
RUN pip install wheel setuptools cython
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir TA-Lib==0.4.0

COPY . .

CMD ["python", "main.py"]
