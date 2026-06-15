import os
from pathlib import Path

# Базовая директория проекта
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Папка для временного хранения загрузок
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Ограничения безопасности
MAX_CROP_DURATION = 3600  # Максимальная длительность обрезки (1 час) в секундах
FILE_LIFETIME = 1800      # Время жизни временных файлов перед удалением (30 минут) в секундах

# CORS
CORS_ORIGINS = ["*"]
