FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN apt-get update && apt-get install -y \
    gcc g++ \
    libatlas-base-dev \
    libblas-dev \
    liblapack-dev \
    gfortran \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel

RUN pip install -r requirements.txt

CMD ["python", "main.py"]

