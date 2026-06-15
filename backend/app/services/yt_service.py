import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from app.config import DOWNLOAD_DIR, MAX_CROP_DURATION, COOKIES_FILE, BASE_DIR
from app.schemas.downloader import VideoFormatInfo, AnalyzeResponse
from app.services.task_manager import task_manager

# Регулярное выражение для парсинга прогресса yt-dlp
# Примеры:
# [download]  12.5% of  15.00MiB at  3.20MiB/s ETA 00:04
# [download]  45.3% of ~ 20.10MiB at    1.25MiB/s ETA 00:10 (frag 4/12)
PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<percent>\d+(?:\.\d+)?)%\s+of\s+(?:~?\s*)(?P<size>[0-9.]+[A-Za-z]+)(?:.*?)at\s+(?:~?\s*)(?P<speed>[0-9.]+[A-Za-z]+/s)(?:.*?)ETA\s+(?P<eta>[\d:]+)"
)

def parse_time_to_seconds(t_str: str) -> int:
    parts = t_str.strip().split(':')
    if len(parts) == 1:
        return int(parts[0])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    else:
        raise ValueError("Неверный формат времени. Используйте ЧЧ:ММ:СС, ММ:СС или секунды.")

def format_seconds_to_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def setup_ffmpeg_path() -> bool:
    if shutil.which("ffmpeg"):
        return True
        
    # Ищем в WinGet Packages
    winget_packages_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.exists(winget_packages_dir):
        import glob
        ffmpeg_bins = glob.glob(os.path.join(winget_packages_dir, "Gyan.FFmpeg*", "*", "bin"))
        if ffmpeg_bins:
            bin_path = ffmpeg_bins[0]
            os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
            print(f"[PATH] Добавлен путь к ffmpeg: {bin_path}")
            return True
            
    # Ищем также в Program Files
    program_files_dir = os.path.expandvars(r"%ProgramFiles%")
    if os.path.exists(program_files_dir):
        import glob
        ffmpeg_bins = glob.glob(os.path.join(program_files_dir, "ffmpeg*", "bin"))
        if ffmpeg_bins:
            bin_path = ffmpeg_bins[0]
            os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
            print(f"[PATH] Добавлен путь к ffmpeg: {bin_path}")
            return True
            
    return False

async def check_ffmpeg() -> bool:
    # 1. Проверяем наличие скачанного ffmpeg.exe в папке проекта или рядом с .exe
    if getattr(sys, 'frozen', False):
        ffmpeg_path = Path(sys.executable).parent / "ffmpeg.exe"
    else:
        ffmpeg_path = BASE_DIR / "ffmpeg.exe"
        
    if ffmpeg_path.exists():
        return True
        
    # 2. Проверяем системный PATH и другие пути
    return setup_ffmpeg_path() or shutil.which("ffmpeg") is not None

def get_browser_from_ua(ua: str) -> Optional[str]:
    if not ua:
        return None
    ua = ua.lower()
    if "edg/" in ua or "edge/" in ua:
        return "edge"
    elif "opr/" in ua or "opera/" in ua:
        return "opera"
    elif "brave" in ua:
        return "brave"
    elif "firefox" in ua:
        return "firefox"
    elif "chrome" in ua:
        return "chrome"
    elif "safari" in ua and "chrome" not in ua:
        return "safari"
    return None

def get_browsers_ordered_by_cookies() -> List[str]:
    if sys.platform != "win32":
        return []
        
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    app_data = os.environ.get("APPDATA", "")
    
    import glob
    cookie_patterns = {
        "chrome": [
            os.path.join(local_app_data, "Google", "Chrome", "User Data", "Default", "Network", "Cookies"),
            os.path.join(local_app_data, "Google", "Chrome", "User Data", "Profile *", "Network", "Cookies"),
            os.path.join(local_app_data, "Google", "Chrome", "User Data", "Default", "Cookies"),
        ],
        "edge": [
            os.path.join(local_app_data, "Microsoft", "Edge", "User Data", "Default", "Network", "Cookies"),
            os.path.join(local_app_data, "Microsoft", "Edge", "User Data", "Profile *", "Network", "Cookies"),
        ],
        "firefox": [
            os.path.join(app_data, "Mozilla", "Firefox", "Profiles", "*", "cookies.sqlite"),
        ],
        "brave": [
            os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "User Data", "Default", "Network", "Cookies"),
            os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "User Data", "Profile *", "Network", "Cookies"),
        ],
        "opera": [
            os.path.join(app_data, "Opera Software", "Opera Stable", "Network", "Cookies"),
            os.path.join(app_data, "Opera Software", "Opera Stable", "Cookies"),
        ],
    }
    
    browser_mtimes = []
    
    for browser, patterns in cookie_patterns.items():
        max_mtime = 0
        for pattern in patterns:
            for filepath in glob.glob(pattern):
                try:
                    if os.path.exists(filepath):
                        mtime = os.path.getmtime(filepath)
                        if mtime > max_mtime:
                            max_mtime = mtime
                except Exception:
                    pass
        if max_mtime > 0:
            browser_mtimes.append((browser, max_mtime))
            
    browser_mtimes.sort(key=lambda x: x[1], reverse=True)
    return [b[0] for b in browser_mtimes]

def get_candidate_browsers(client_browser: str = None) -> List[str]:
    # На удаленном сервере (Linux) нет доступа к браузерам пользователя,
    # поэтому попытки прочитать куки из локальных путей приведут только к задержкам.
    if sys.platform != "win32":
        return []
        
    system_browsers = get_browsers_ordered_by_cookies()
    candidates = []
    
    if client_browser in ["chrome", "edge", "firefox", "brave", "opera", "safari"]:
        candidates.append(client_browser)
        
    for b in system_browsers:
        if b not in candidates:
            candidates.append(b)
            
    if not candidates:
        candidates = ["chrome", "edge", "firefox", "brave", "opera"]
        
    return candidates

async def extract_video_info(url: str, client_browser: str = None) -> AnalyzeResponse:
    # Запускаем yt-dlp для получения JSON
    def run_sync(use_cookies: bool, browser_name: str = None):
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        ytdlp_cmd = ["--ytdlp-worker"] if getattr(sys, 'frozen', False) else ["-m", "yt_dlp"]
        args = [sys.executable] + ytdlp_cmd + [
            "--dump-json",
            "--no-warnings",
            "--no-playlist",
            "--no-check-certificate",
            "--impersonate", "chrome",
        ]
        
        if use_cookies:
            if browser_name == "custom_file" and COOKIES_FILE.exists():
                args.extend(["--cookies", str(COOKIES_FILE)])
                print(f"[Cookies] Использование загруженного файла кук: {COOKIES_FILE}")
            elif browser_name and browser_name != "custom_file":
                args.extend(["--cookies-from-browser", browser_name])
                print(f"[Cookies] Попытка использовать куки браузера: {browser_name}")
            
        if shutil.which("node"):
            args.extend(["--js-runtimes", "node", "--remote-components", "ejs:github"])
            
        args.append(url)
        
        return subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo
        )

    result = None
    last_error_msg = ""
    
    # 1. Сначала пробуем загруженный файл кук, если он есть
    if COOKIES_FILE.exists():
        print(f"[Info] Пробуем получить информацию с использованием загруженного файла кук...")
        res = await asyncio.to_thread(run_sync, use_cookies=True, browser_name="custom_file")
        if res.returncode == 0:
            result = res
        else:
            last_error_msg = res.stderr.decode('utf-8', errors='replace').strip()
            print(f"[Cookies] Загруженный файл кук не сработал: {last_error_msg}")

    # 2. Если файл кук не сработал или его нет, пробуем браузеры по очереди
    if result is None:
        browsers_to_try = get_candidate_browsers(client_browser)
        for browser in browsers_to_try:
            print(f"[Info] Пробуем получить информацию с использованием кук браузера: {browser}")
            res = await asyncio.to_thread(run_sync, use_cookies=True, browser_name=browser)
            stdout, stderr = res.stdout, res.stderr
            error_msg = stderr.decode('utf-8', errors='replace').strip()
            
            if res.returncode == 0:
                result = res
                break
            else:
                last_error_msg = error_msg
                print(f"[Cookies] Ошибка при использовании браузера {browser}: {error_msg}")
                if "Incomplete YouTube ID" in error_msg or "is not a valid URL" in error_msg:
                    break

    # 3. Если с куками ни один браузер не сработал, пробуем без кук
    if result is None:
        if "Incomplete YouTube ID" in last_error_msg or "is not a valid URL" in last_error_msg:
            raise ValueError("Невалидный URL-адрес YouTube.")
            
        print("[Info] Пробуем получить информацию без использования кук...")
        res = await asyncio.to_thread(run_sync, use_cookies=False)
        stdout, stderr = res.stdout, res.stderr
        if res.returncode == 0:
            result = res
        else:
            error_msg = stderr.decode('utf-8', errors='replace').strip()
            if "Incomplete YouTube ID" in error_msg or "is not a valid URL" in error_msg:
                raise ValueError("Невалидный URL-адрес YouTube.")
            elif "Video unavailable" in error_msg or "Sign in to confirm" in error_msg:
                raise ValueError("Видео недоступно (удалено, приватное или требует авторизации/кук).")
            else:
                raise ValueError(f"Ошибка yt-dlp: {error_msg}")
            
    info = json.loads(stdout.decode('utf-8', errors='replace'))
    
    title = info.get("title", "Без названия")
    author = info.get("uploader") or info.get("channel", "Неизвестно")
    duration = int(info.get("duration", 0))
    thumbnail = info.get("thumbnail")
    
    # Извлекаем доступные форматы
    raw_formats = info.get("formats", [])
    
    # Нам нужны уникальные разрешения (высота кадра). 
    # Собираем высоты для видеопотоков (где vcodec != none)
    heights = set()
    for f in raw_formats:
        h = f.get("height")
        if h and f.get("vcodec") != "none":
            heights.add(h)
            
    sorted_heights = sorted(list(heights), reverse=True)
    
    formats_list = []
    
    # Добавляем видеоформаты
    for height in sorted_heights:
        # Для отображения пользователю
        res_name = f"{height}p"
        
        # Найдем лучший формат для этой высоты для оценки размера
        matching_formats = [f for f in raw_formats if f.get("height") == height and f.get("vcodec") != "none"]
        best_match = matching_formats[0] if matching_formats else {}
        
        filesize = best_match.get("filesize") or best_match.get("filesize_approx")
        filesize_mb = round(filesize / (1024 * 1024), 2) if filesize else None
        
        formats_list.append(VideoFormatInfo(
            format_id=f"res:{height}",
            resolution=res_name,
            height=height,
            ext="mp4",
            filesize_mb=filesize_mb,
            fps=best_match.get("fps"),
            note=best_match.get("format_note")
        ))
        
    # Всегда добавляем опцию "Только аудио"
    formats_list.append(VideoFormatInfo(
        format_id="bestaudio/best",
        resolution="audio",
        ext="mp3",
        note="Только аудиопоток (MP3)"
    ))
    
    return AnalyzeResponse(
        title=title,
        author=author,
        duration=duration,
        duration_formatted=format_seconds_to_time(duration),
        thumbnail=thumbnail,
        formats=formats_list
    )

async def download_video_task(
    task_id: str,
    url: str,
    resolution: str,
    need_crop: bool,
    crop_start: str = None,
    crop_end: str = None,
    client_browser: str = None
):
    task = await task_manager.get_task(task_id)
    if not task:
        return

    # Проверка наличия ffmpeg
    if not await check_ffmpeg():
        task.update(status="failed", error="ffmpeg не установлен в системе. Пожалуйста, установите ffmpeg для поддержки слияния и обрезки видео.")
        return

    # Подготовка путей
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{task_id}.%(ext)s")
    
    # Базовые аргументы для yt-dlp
    ytdlp_cmd = ["--ytdlp-worker"] if getattr(sys, 'frozen', False) else ["-m", "yt_dlp"]
    base_args = [sys.executable] + ytdlp_cmd + [
        "--no-playlist",
        "--no-warnings",
        "--progress",
        "--newline",
        "--no-check-certificate",
        "--impersonate", "chrome",
        "-N", "6",  # Безопасное число потоков (16 вызывает блокировку от YouTube)
        "-o", outtmpl,
    ]
    
    # Автоматический выбор JS-рантайма
    if shutil.which("node"):
        base_args.extend(["--js-runtimes", "node", "--remote-components", "ejs:github"])
    
    # Настройка формата
    is_audio = resolution.lower() == "audio"
    if is_audio:
        base_args.extend([
            "-f", "bestaudio/best",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0"
        ])
    else:
        # resolution вида "1080p", "720p" и т.д.
        format_str = "bv*+ba/b"
        try:
            height = int(resolution.replace("p", ""))
            base_args.extend(["-S", f"res:{height}"])
        except ValueError:
            pass
            
        base_args.extend([
            "-f", format_str,
            "--merge-output-format", "mp4"
        ])

    # Настройка обрезки
    if need_crop and crop_start and crop_end:
        try:
            start_sec = parse_time_to_seconds(crop_start)
            end_sec = parse_time_to_seconds(crop_end)
            duration = end_sec - start_sec
            
            if duration <= 0:
                task.update(status="failed", error="Время конца обрезки должно быть больше времени начала.")
                return
            if duration > MAX_CROP_DURATION:
                task.update(status="failed", error=f"Превышена максимальная длительность обрезки ({MAX_CROP_DURATION // 60} мин).")
                return
                
            base_args.extend([
                "--download-sections", f"*{crop_start}-{crop_end}",
                "--force-keyframes-at-cuts"
            ])
        except ValueError as e:
            task.update(status="failed", error=str(e))
            return

    # Добавляем URL
    base_args.append(url)
    
    # Добавляем путь к ffmpeg, если он скачан
    if getattr(sys, 'frozen', False):
        ffmpeg_path = Path(sys.executable).parent / "ffmpeg.exe"
    else:
        ffmpeg_path = BASE_DIR / "ffmpeg.exe"
        
    if ffmpeg_path.exists():
        base_args.extend(["--ffmpeg-location", str(ffmpeg_path)])
    
    # Запуск загрузки
    task.update(status="downloading", progress=0)
    
    loop = asyncio.get_running_loop()
    
    def update_task(**kwargs):
        loop.call_soon_threadsafe(lambda: task.update(**kwargs))

    browsers_to_try = get_candidate_browsers(client_browser)

    def run_sync_download(use_cookies: bool, browser_name: str = None):
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        cmd_args = base_args.copy()
        if use_cookies:
            if browser_name == "custom_file" and COOKIES_FILE.exists():
                cmd_args.insert(3, "--cookies")
                cmd_args.insert(4, str(COOKIES_FILE))
                print(f"[Download Cookies] Использование загруженного файла кук: {COOKIES_FILE}")
            elif browser_name and browser_name != "custom_file":
                cmd_args.insert(3, "--cookies-from-browser")
                cmd_args.insert(4, browser_name)
                print(f"[Download Cookies] Попытка использовать куки браузера: {browser_name}")
            
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo
        )
        
        # Чтение вывода yt-dlp построчно
        for line_bytes in iter(process.stdout.readline, b''):
            line = line_bytes.decode('utf-8', errors='replace').strip()
            
            # Парсинг прогресса скачивания
            match = PROGRESS_RE.search(line)
            if match:
                try:
                    percent = int(float(match.group("percent")))
                    speed = match.group("speed")
                    eta = match.group("eta")
                    update_task(progress=percent, speed=speed, eta=eta)
                except Exception:
                    pass
            elif "[download]" in line and "%" in line:
                try:
                    perc_str = re.search(r"(\d+(?:\.\d+)?)%", line)
                    if perc_str:
                        percent = int(float(perc_str.group(1)))
                        update_task(progress=percent)
                except Exception:
                    pass
                
            # Парсинг процесса слияния или конвертации
            elif "[Merger]" in line or "Merging formats into" in line:
                update_task(status="processing", progress=95, speed="N/A", eta="Merge...")
            elif "[ExtractAudio]" in line:
                update_task(status="processing", progress=98, speed="N/A", eta="Convert...")
                
        stderr_data = process.stderr.read()
        returncode = process.wait()
        return returncode, stderr_data

    try:
        returncode = -1
        stderr_data = b""
        result_found = False
        
        # 1. Пробуем сначала загруженный файл кук
        if COOKIES_FILE.exists():
            print(f"[Download] Пробуем скачать с использованием загруженного файла кук...")
            returncode, stderr_data = await asyncio.to_thread(run_sync_download, use_cookies=True, browser_name="custom_file")
            if returncode == 0:
                result_found = True
            else:
                error_msg = stderr_data.decode('utf-8', errors='replace').strip()
                print(f"[Download] Ошибка при скачивании с загруженными куками: {error_msg}")
        
        # 2. Если файл кук не сработал, пробуем каждый браузер по очереди
        if not result_found:
            for browser in browsers_to_try:
                print(f"[Download] Пробуем скачать с использованием кук браузера: {browser}")
                returncode, stderr_data = await asyncio.to_thread(run_sync_download, use_cookies=True, browser_name=browser)
                if returncode == 0:
                    result_found = True
                    break
                else:
                    error_msg = stderr_data.decode('utf-8', errors='replace').strip()
                    print(f"[Download] Ошибка при скачивании с куками {browser}: {error_msg}")
                    # Если ошибка вызвана некорректной обрезкой, прекращаем цикл
                    if "crop" in error_msg.lower() or "sections" in error_msg.lower():
                        break
                        
        # 3. Если с куками не вышло, пробуем без кук
        if not result_found:
            error_msg = stderr_data.decode('utf-8', errors='replace').strip()
            if not ("crop" in error_msg.lower() or "sections" in error_msg.lower()):
                print("[Download] Пробуем скачать без использования кук...")
                returncode, stderr_data = await asyncio.to_thread(run_sync_download, use_cookies=False)
                
        if returncode != 0:
            error_msg = stderr_data.decode('utf-8', errors='replace').strip()
            
            # Логируем детальную отладочную информацию в файл
            debug_info = (
                f"URL: {url}\n"
                f"RESOLUTION: {resolution}\n"
                f"NEED_CROP: {need_crop}\n"
                f"COOKIES_FILE_EXISTS: {COOKIES_FILE.exists()}\n"
                f"ERROR: {error_msg}\n"
            )
            try:
                ytdlp_cmd = ["--ytdlp-worker"] if getattr(sys, 'frozen', False) else ["-m", "yt_dlp"]
                debug_args = [sys.executable] + ytdlp_cmd + ["--list-formats"]
                if COOKIES_FILE.exists():
                    debug_args.extend(["--cookies", str(COOKIES_FILE)])
                debug_args.append(url)
                
                res_debug = subprocess.run(debug_args, capture_output=True, text=True)
                debug_info += f"\n--- LIST FORMATS OUT ---\n{res_debug.stdout}\n{res_debug.stderr}"
            except Exception as e:
                debug_info += f"\nFailed to list formats: {str(e)}"
                
            debug_file_path = os.path.join(DOWNLOAD_DIR, "ytdl_debug.txt")
            try:
                with open(debug_file_path, "w", encoding="utf-8") as f:
                    f.write(debug_info)
                print(f"[Debug] Лог сохранен в {debug_file_path}")
            except Exception as e:
                print(f"[Debug] Не удалось сохранить лог: {e}")
                
            task.update(status="failed", error=f"Ошибка скачивания: {error_msg}")
            return
            
        # Поиск финального файла на диске
        import glob
        final_files = [f for f in glob.glob(os.path.join(DOWNLOAD_DIR, f"{task_id}.*")) if not f.endswith((".part", ".ytdl"))]
        
        if not final_files:
            task.update(status="failed", error="Файл не был создан.")
            return
            
        file_path = final_files[0]
        ext = os.path.splitext(file_path)[1]
        
        # Получаем оригинальное имя видео (для переименования при скачивании)
        # Получим его асинхронно
        title_clean = re.sub(r'[\\/*?:"<>|]', "", task.filename or "video")
        download_filename = f"{title_clean}{ext}"
        
        task.update(
            status="completed",
            progress=100,
            file_path=file_path,
            filename=download_filename
        )
        
        # Сохранение лога в базу данных (если включено)
        from app.database import save_download_record
        await save_download_record(
            task_id=task_id,
            url=url,
            title=download_filename,
            resolution=resolution,
            file_path=file_path
        )
        
    except Exception as e:
        task.update(status="failed", error=f"Внутренняя ошибка: {str(e)}")
