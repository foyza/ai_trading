FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y build-essential curl && \
    curl -L https://github.com/mrjbq7/ta-lib/releases/download/0.4.0/ta-lib-0.4.0-src.tar.gz | tar xz && \
    cd ta-lib && ./configure && make && make install && cd .. && rm -rf ta-lib && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
