import os
from pathlib import Path

import sys

if getattr(sys, 'frozen', False):
    # Приложение запущено как скомпилированный .exe
    BASE_DIR = Path(sys._MEIPASS)
    # Загрузки и куки сохраняем рядом с самим .exe файлом (чтобы не потерялись после закрытия)
    EXE_DIR = Path(sys.executable).parent
    DOWNLOAD_DIR = EXE_DIR / "downloads"
else:
    # Обычный запуск (исходный код)
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DOWNLOAD_DIR = BASE_DIR / "downloads"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Ограничения безопасности
MAX_CROP_DURATION = 3600  # Максимальная длительность обрезки (1 час) в секундах
FILE_LIFETIME = 1800      # Время жизни временных файлов перед удалением (30 минут) в секундах

# CORS
CORS_ORIGINS = ["*"]

# Настройки базы данных (выключено по умолчанию)
SAVE_TO_DATABASE = os.getenv("SAVE_TO_DATABASE", "False").lower() in ("true", "1", "yes")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bagatube.db")

# Путь к файлу кук YouTube
COOKIES_FILE = DOWNLOAD_DIR / "youtube_cookies.txt"


