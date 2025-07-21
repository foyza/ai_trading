FROM python:3.11

RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    curl \
    git \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /usr/src/ta-lib && \
    cd /usr/src/ta-lib && \
    wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && \
    ./configure --prefix=/usr && \
    make && \
    make install

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
