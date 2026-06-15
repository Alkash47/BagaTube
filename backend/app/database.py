import os
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime

from app.config import SAVE_TO_DATABASE, DATABASE_URL

# Инициализируем объекты только если база данных включена
engine = None
SessionLocal = None

if SAVE_TO_DATABASE and DATABASE_URL:
    connect_args = {}
    if DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        
    engine = create_async_engine(DATABASE_URL, connect_args=connect_args, echo=False)
    SessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

class Base(DeclarativeBase):
    pass

class DownloadRecord(Base):
    __tablename__ = "download_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    url: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str] = mapped_column(String(255))
    resolution: Mapped[str] = mapped_column(String(20))
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # длительность видео в секундах
    file_path: Mapped[str] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

async def init_db():
    """Создает таблицы в базе данных при запуске приложения, если SAVE_TO_DATABASE включен."""
    if SAVE_TO_DATABASE and engine:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print("[Database] Таблицы базы данных успешно инициализированы.")
        except Exception as e:
            print(f"[Database] Ошибка инициализации базы данных: {e}")

async def save_download_record(task_id: str, url: str, title: str, resolution: str, file_path: str):
    """Сохраняет запись о скачанном видео в базу данных, если это включено."""
    if not SAVE_TO_DATABASE or not SessionLocal:
        return
    try:
        async with SessionLocal() as session:
            async with session.begin():
                record = DownloadRecord(
                    task_id=task_id,
                    url=url,
                    title=title[:255],  # обрезаем до 255 символов (длина String(255) в модели)
                    resolution=resolution,
                    file_path=file_path
                )
                session.add(record)
            print(f"[Database] Успешно сохранен лог скачивания для задачи {task_id}")
    except Exception as e:
        print(f"[Database] Ошибка при сохранении лога скачивания в БД: {e}")
