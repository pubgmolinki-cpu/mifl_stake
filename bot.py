import asyncio
import logging
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher

# Вот ТУТ исправлен импорт: вместо aiohttp_handler теперь правильный aiohttp_server
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import config
from database import db

# Напрямую импортируем роутеры твоих модулей
from handlers.user import router as user_router
from handlers.bets import router as bets_router
from handlers.admin import router as admin_router

# Логирование для вывода в консоль Render
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot) -> None:
    try:
        logger.info("⏳ Шаг 1: Подключение к базе данных PostgreSQL...")
        await db.connect()
        
        logger.info(f"⏳ Шаг 2: Установка вебхука на адрес: {config.WEBHOOK_URL}")
        await bot.set_webhook(config.WEBHOOK_URL)
        logger.info("🎉 Вебхук успешно установлен, бот готов принимать сообщения!")
    except Exception as e:
        logger.critical(f"💥 КРИТИЧЕСКАЯ ОШИБКА НА СТАРТЕ БОТА: {e}", exc_info=True)
        sys.exit(1)

def main():
    try:
        logger.info("🔎 Проверка переменных окружения в Render...")
        if not config.BOT_TOKEN:
            raise ValueError("❌ Ошибка: Переменная 'BOT_TOKEN' пустая или отсутствует!")
        if not config.DATABASE_URL:
            raise ValueError("❌ Ошибка: Переменная 'DATABASE_URL' пустая или отсутствует!")
        if not config.WEBHOOK_HOST:
            raise ValueError("❌ Ошибка: Переменная 'WEBHOOK_HOST' пустая или отсутствует!")

        logger.info("🤖 Инициализация компонентов aiogram...")
        bot = Bot(token=config.BOT_TOKEN)
        dp = Dispatcher()

        # Регистрация обработчиков
        dp.include_routers(admin_router, user_router, bets_router)

        # Привязываем метод старта
        dp.startup.register(on_startup)

        # Конфигурация вебхук-сервера на aiohttp
        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

        logger.info(f"📡 Запуск сервера aiohttp на порту {config.PORT}...")
        web.run_app(app, host="0.0.0.0", port=config.PORT)

    except Exception as e:
        logger.critical(f"💥 Бот упал во время инициализации main(): {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
