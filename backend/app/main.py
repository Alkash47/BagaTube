import asyncio
import os
import sys
import time

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from app.config import CORS_ORIGINS, DOWNLOAD_DIR, FILE_LIFETIME, BASE_DIR
from app.routers import downloader

async def cleanup_worker():
    """
    Фоновый процесс, который каждые 15 минут сканирует папку downloads
    и удаляет файлы, время последнего изменения которых превышает FILE_LIFETIME.
    """
    print("[Cleanup Worker] Фоновый очиститель запущен.")
    while True:
        try:
            await asyncio.sleep(900)  # Интервал проверки 15 минут (900 секунд)
            print("[Cleanup Worker] Проверка устаревших файлов...")
            now = time.time()
            if os.path.exists(DOWNLOAD_DIR):
                for filename in os.listdir(DOWNLOAD_DIR):
                    file_path = os.path.join(DOWNLOAD_DIR, filename)
                    if os.path.isfile(file_path):
                        # Не трогаем временные файлы активных загрузок (.part / .ytdl)
                        if file_path.endswith((".part", ".ytdl")):
                            continue
                        
                        mtime = os.path.getmtime(file_path)
                        if now - mtime > FILE_LIFETIME:
                            try:
                                os.remove(file_path)
                                print(f"[Cleanup Worker] Удален устаревший файл: {file_path}")
                            except Exception as e:
                                print(f"[Cleanup Worker] Не удалось удалить {file_path}: {e}")
        except asyncio.CancelledError:
            print("[Cleanup Worker] Очиститель останавливается...")
            break
        except Exception as e:
            print(f"[Cleanup Worker] Ошибка в работе очистителя: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаем папку для загрузок на старте
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Запускаем фоновый воркер очистки файлов
    cleanup_task = asyncio.create_task(cleanup_worker())
    yield
    # При остановке приложения отменяем задачу очистки
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="BagaTube API",
    description="API для скачивания и обрезки видеороликов с YouTube с отслеживанием прогресса через SSE",
    version="1.0.0",
    lifespan=lifespan
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(downloader.router)

# Раздача фронтенда: главная страница
@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = BASE_DIR / "static" / "index.html"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse(
        content="<h1>Файлы фронтенда не найдены!</h1><p>Убедитесь, что папка static создана и содержит index.html.</p>",
        status_code=404
    )

# Монтирование статических файлов (css, js, картинки)
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")
