import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_handler import SimpleRequestHandler, setup_application

from config import BOT_TOKEN, PORT, WEBHOOK_URL, WEBHOOK_PATH
from database import db
from handlers import user, bets, admin

logging.basicConfig(level=logging.INFO)

async def on_startup(bot: Bot) -> None:
    # Инициализируем базу данных
    await db.connect()
    
    # Говорим Телеграму отправлять все события на наш адрес на Render
    await bot.set_webhook(WEBHOOK_URL)
    print(f"🚀 Вебхук успешно установлен на: {WEBHOOK_URL}")

def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем обработчики команд
    dp.include_routers(admin.router, user.router, bets.router)

    # Регистрируем функцию, которая выполнится при старте сервера
    dp.startup.register(on_startup)

    # Создаем веб-приложение aiohttp
    app = web.Application()

    # Настраиваем обработчик запросов от Telegram
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    # Регистрируем бота внутри веб-приложения
    setup_application(app, dp, bot=bot)

    print(f"🤖 Бот запускается на порту {PORT}...")
    
    # Запускаем сервер на хосте 0.0.0.0 (требование Render) и нужном порту
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
