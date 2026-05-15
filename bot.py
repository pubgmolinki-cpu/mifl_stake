import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database import db
from handlers import user, bets, admin

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем роутеры обработчиков
    dp.include_routers(admin.router, user.router, bets.router)

    # Инициализация пула БД перед запуском пуллинга
    await db.connect()

    print("🤖 Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
