import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

ADMIN_IDS = [1866813859]  # Твой ID

# --- НАСТРОЙКИ ДЛЯ RENDER (WEBHOOK) ---
# Render автоматически выдает порт в переменную окружения PORT. Если ее нет (локально), ставим 8080
PORT = int(os.getenv("PORT", 8080))

# Ссылка на твое приложение Render (например: https://ftcl-bet.onrender.com)
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST") 
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
