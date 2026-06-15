FROM python:3.11-slim

# Установка системных зависимостей (ffmpeg для слияния/обрезки видео, nodejs для yt-dlp)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование требований и установка python-пакетов
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода бэкенда и статического фронтенда
COPY backend ./backend
COPY static ./static

# Создание папки для временных файлов
RUN mkdir -p downloads && chmod 777 downloads

# Настройка переменных окружения
ENV PORT=7860
ENV PYTHONPATH=/app/backend

# Открытие порта 7860
EXPOSE 7860

# Запуск приложения через uvicorn
CMD uvicorn app.main:app --host 0.0.0.0 --port 7860
