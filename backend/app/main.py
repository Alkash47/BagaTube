import asyncio
import os
import sys
import time
from pathlib import Path

# Обработка вызова yt-dlp внутри скомпилированного .exe
if len(sys.argv) >= 2 and sys.argv[1] == "--ytdlp-worker":
    import yt_dlp
    sys.argv.pop(1)
    yt_dlp.main()
    sys.exit(0)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from app.config import CORS_ORIGINS, DOWNLOAD_DIR, FILE_LIFETIME, BASE_DIR
from app.routers import downloader
from app.database import init_db

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
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    await init_db()
    cleanup_task = asyncio.create_task(cleanup_worker())
    yield
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(downloader.router)

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

static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

def ensure_ffmpeg():
    import urllib.request
    import zipfile
    
    if getattr(sys, 'frozen', False):
        target_dir = Path(sys.executable).parent
    else:
        target_dir = BASE_DIR
        
    ffmpeg_exe = target_dir / "ffmpeg.exe"
    if ffmpeg_exe.exists():
        return
        
    print("[Setup] ffmpeg не найден. Скачивание (это займет около минуты)...")
    url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    zip_path = target_dir / "ffmpeg_temp.zip"
    
    try:
        urllib.request.urlretrieve(url, zip_path)
        print("[Setup] Извлечение ffmpeg...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                if file_info.filename.endswith("ffmpeg.exe"):
                    file_info.filename = "ffmpeg.exe"
                    zip_ref.extract(file_info, target_dir)
                elif file_info.filename.endswith("ffprobe.exe"):
                    file_info.filename = "ffprobe.exe"
                    zip_ref.extract(file_info, target_dir)
        print("[Setup] ffmpeg успешно установлен!")
    except Exception as e:
        print(f"[Setup] Ошибка при скачивании ffmpeg: {e}")
    finally:
        if zip_path.exists():
            zip_path.unlink()

if __name__ == "__main__":
    ensure_ffmpeg()
    import uvicorn
    import multiprocessing
    multiprocessing.freeze_support()
    uvicorn.run(app, host="127.0.0.1", port=7860)
