from typing import List, Optional
from pydantic import BaseModel, HttpUrl

class AnalyzeRequest(BaseModel):
    url: str

class VideoFormatInfo(BaseModel):
    format_id: str
    resolution: str
    height: Optional[int] = None
    ext: str
    filesize_mb: Optional[float] = None
    fps: Optional[int] = None
    note: Optional[str] = None

class AnalyzeResponse(BaseModel):
    title: str
    author: Optional[str] = None
    duration: int  # в секундах
    duration_formatted: str  # HH:MM:SS
    thumbnail: Optional[str] = None
    formats: List[VideoFormatInfo]

class DownloadRequest(BaseModel):
    url: str
    resolution: str  # например, "1080p", "720p", "480p", "360p", "audio"
    title: Optional[str] = None  # оригинальное название видео для имени файла
    need_crop: bool = False
    crop_start: Optional[str] = None  # HH:MM:SS или MM:SS
    crop_end: Optional[str] = None    # HH:MM:SS или MM:SS

class DownloadResponse(BaseModel):
    task_id: str

class CookieStatusResponse(BaseModel):
    has_cookies: bool
    filename: Optional[str] = None
    mtime: Optional[float] = None

class SaveCookiesRequest(BaseModel):
    cookies_text: str

