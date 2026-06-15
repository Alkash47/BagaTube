import asyncio
import os
import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Request, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from app.schemas.downloader import (
    AnalyzeRequest, AnalyzeResponse, DownloadRequest, DownloadResponse,
    CookieStatusResponse, SaveCookiesRequest
)
from app.services.task_manager import task_manager
from app.services.yt_service import extract_video_info, download_video_task, get_browser_from_ua
from app.config import COOKIES_FILE, DOWNLOAD_DIR

router = APIRouter(prefix="/api/downloader", tags=["downloader"])

async def delete_file_after_delay(file_path: str, task_id: str):
    # Задержка 10 секунд перед удалением файла, чтобы дать клиенту полностью скачать его
    await asyncio.sleep(10)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[Cleanup] Успешно удален файл задачи {task_id}: {file_path}")
    except Exception as e:
        print(f"[Cleanup] Ошибка при удалении файла {file_path}: {e}")
    finally:
        await task_manager.delete_task(task_id)

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_url(request: AnalyzeRequest, fastapi_request: Request):
    try:
        user_agent = fastapi_request.headers.get("user-agent", "")
        browser = get_browser_from_ua(user_agent)
        info = await extract_video_info(request.url, client_browser=browser)
        return info
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка при анализе видео: {str(e)}"
        )

@router.post("/download", response_model=DownloadResponse)
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks, fastapi_request: Request):
    task_id = str(uuid.uuid4())
    
    # Создаем задачу в менеджере
    task = await task_manager.create_task(task_id)
    
    # Устанавливаем имя файла на основе переданного заголовка
    if request.title:
        task.update(filename=request.title)
    
    user_agent = fastapi_request.headers.get("user-agent", "")
    browser = get_browser_from_ua(user_agent)
    
    # Запускаем задачу скачивания в фоне через FastAPI BackgroundTasks
    background_tasks.add_task(
        download_video_task,
        task_id=task_id,
        url=request.url,
        resolution=request.resolution,
        need_crop=request.need_crop,
        crop_start=request.crop_start,
        crop_end=request.crop_end,
        client_browser=browser
    )
    
    return DownloadResponse(task_id=task_id)

@router.get("/tasks/{task_id}/progress")
async def get_progress(task_id: str):
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена"
        )
        
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream",
        "X-Accel-Buffering": "no"  # Отключает буферизацию в Nginx
    }
    
    return StreamingResponse(
        task_manager.subscribe(task_id),
        headers=headers
    )

@router.get("/files/{task_id}")
async def get_file(task_id: str, background_tasks: BackgroundTasks):
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или устарела"
        )
        
    if task.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Файл еще не готов. Статус: {task.status}"
        )
        
    if not task.file_path or not os.path.exists(task.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл не найден на сервере"
        )
        
    # Добавляем задачу удаления файла в фон после отдачи клиенту
    background_tasks.add_task(delete_file_after_delay, task.file_path, task_id)
    
    return FileResponse(
        path=task.file_path,
        filename=task.filename,
        media_type="application/octet-stream"
    )

@router.get("/cookies/status", response_model=CookieStatusResponse)
async def get_cookies_status():
    if COOKIES_FILE.exists():
        try:
            stat = os.stat(COOKIES_FILE)
            return CookieStatusResponse(
                has_cookies=True,
                filename=COOKIES_FILE.name,
                mtime=stat.st_mtime
            )
        except Exception:
            pass
    return CookieStatusResponse(has_cookies=False)

@router.post("/cookies")
async def save_cookies_text(payload: SaveCookiesRequest):
    try:
        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        text = payload.cookies_text.strip()
        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пустое содержимое кук"
            )
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(text)
        return {"status": "success", "message": "Куки успешно сохранены"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось сохранить куки: {str(e)}"
        )

@router.post("/cookies/upload")
async def upload_cookies_file(file: UploadFile = File(...)):
    try:
        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        text = content.decode("utf-8", errors="replace").strip()
        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пустой файл кук"
            )
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(text)
        return {"status": "success", "message": f"Файл {file.filename} успешно загружен и сохранен"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось загрузить файл кук: {str(e)}"
        )

@router.delete("/cookies")
async def delete_cookies():
    try:
        if COOKIES_FILE.exists():
            os.remove(COOKIES_FILE)
            return {"status": "success", "message": "Куки успешно удалены"}
        return {"status": "success", "message": "Куки уже отсутствуют на сервере"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось удалить куки: {str(e)}"
        )

@router.get("/debug")
async def get_debug_log():
    debug_file = os.path.join(DOWNLOAD_DIR, "ytdl_debug.txt")
    if os.path.exists(debug_file):
        try:
            with open(debug_file, "r", encoding="utf-8") as f:
                content = f.read()
            return HTMLResponse(content=f"<html><body><h2>Лог отладки yt-dlp</h2><pre style='background:#f4f4f4;padding:15px;border:1px solid #ccc;overflow:auto;'>{content}</pre></body></html>")
        except Exception as e:
            return HTMLResponse(content=f"<h3>Ошибка чтения лога: {str(e)}</h3>")
    return HTMLResponse(content="<h3>Файл отладки ytdl_debug.txt не найден. Запустите скачивание видео для генерации лога.</h3>")

@router.get("/list_formats")
async def list_remote_formats(url: str):
    import subprocess, sys
    args = [sys.executable, "-m", "yt_dlp", "--list-formats", "--no-warnings"]
    if COOKIES_FILE.exists():
        args.extend(["--cookies", str(COOKIES_FILE)])
    else:
        args.extend(["--extractor-args", "youtube:player_client=android,ios"])
    args.append(url)
    try:
        res = subprocess.run(args, capture_output=True, text=True)
        return HTMLResponse(content=f"<html><body><pre>CMD: {' '.join(args)}\n\nSTDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}</pre></body></html>")
    except Exception as e:
        return HTMLResponse(content=f"<html><body><h3>Error: {str(e)}</h3></body></html>")



