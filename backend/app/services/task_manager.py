import asyncio
import json
from typing import Dict, Optional

class DownloadTask:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.status = "pending"  # pending, downloading, processing, completed, failed
        self.progress = 0        # 0 to 100
        self.speed = ""          # например, "3.4MiB/s"
        self.eta = ""            # например, "00:15"
        self.file_path = None    # путь к готовому файлу
        self.filename = None     # исходное имя файла для скачивания
        self.error = None        # текст ошибки при сбое
        self.event = asyncio.Event()

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.event.set()

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "speed": self.speed,
            "eta": self.eta,
            "filename": self.filename,
            "error": self.error
        }

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, DownloadTask] = {}
        self.lock = asyncio.Lock()

    async def create_task(self, task_id: str) -> DownloadTask:
        async with self.lock:
            task = DownloadTask(task_id)
            self.tasks[task_id] = task
            return task

    async def get_task(self, task_id: str) -> Optional[DownloadTask]:
        async with self.lock:
            return self.tasks.get(task_id)

    async def delete_task(self, task_id: str):
        async with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]

    async def subscribe(self, task_id: str):
        task = await self.get_task(task_id)
        if not task:
            yield f"data: {json.dumps({'error': 'Task not found', 'status': 'failed'})}\n\n"
            return

        # Отправляем начальное состояние
        yield f"data: {json.dumps(task.to_dict(), ensure_ascii=False)}\n\n"

        while task.status not in ("completed", "failed"):
            try:
                # Ожидаем уведомления об изменении состояния задачи
                await asyncio.wait_for(task.event.wait(), timeout=30.0)
                task.event.clear()
                yield f"data: {json.dumps(task.to_dict(), ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                # Отправляем пинг-сообщение для предотвращения разрыва соединения
                yield f"data: {json.dumps(task.to_dict(), ensure_ascii=False)}\n\n"

# Создаем глобальный экземпляр менеджера задач
task_manager = TaskManager()
