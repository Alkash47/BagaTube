import os
import sys
import subprocess
from pathlib import Path

def install_requirements():
    print("[1/3] Установка PyInstaller...")
    # Отключаем прокси на время установки, чтобы избежать ошибки SOCKS
    env = os.environ.copy()
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    env.pop("ALL_PROXY", None)
    env.pop("http_proxy", None)
    env.pop("https_proxy", None)
    env.pop("all_proxy", None)
    subprocess.run([sys.executable, "-m", "pip", "install", "--proxy", "", "pyinstaller"], env=env, check=True)

def build_executable():
    print("[2/3] Сборка .exe файла через PyInstaller...")
    
    # Текущая директория должна быть backend
    current_dir = Path(__file__).resolve().parent
    os.chdir(current_dir)
    
    # Файлы для добавления (static)
    static_src = current_dir.parent / "static"
    add_data = f"{static_src};static"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "BagaTube",
        "--onefile",
        "--console",  # Оставляем консоль для вывода логов
        "--add-data", add_data,
        "--hidden-import", "uvicorn",
        "--hidden-import", "fastapi",
        "--hidden-import", "yt_dlp",
        "--hidden-import", "multipart",
        "--hidden-import", "websockets",
        "--clean",
        "-y",
        "app/main.py"
    ]
    
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    try:
        install_requirements()
        build_executable()
        
        exe_path = Path(__file__).parent / "dist" / "BagaTube.exe"
        print(f"\n[3/3] Сборка завершена успешно!")
        print(f"Готовый файл находится здесь: {exe_path.resolve()}")
    except Exception as e:
        print(f"\nОшибка при сборке: {e}")
