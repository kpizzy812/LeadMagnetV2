# Dockerfile

FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Создание пользователя для приложения
RUN useradd --create-home --shell /bin/bash app

# Установка рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Создание директорий для данных
RUN mkdir -p data/logs data/sessions data/dialogs && \
    chown -R app:app /app

# Переключение на пользователя app
USER app

# Переменная окружения для Python
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose порт (если понадобится веб-интерфейс)
EXPOSE 8000

# Команда по умолчанию
CMD ["python", "main.py"]