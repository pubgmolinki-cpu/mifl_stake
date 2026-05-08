import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, DATABASE_URL
from database import db
from handlers import basic_menu

async def main():
    logging.basicConfig(level=logging.INFO)
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Подключаем папку с кнопками
    dp.include_router(basic_menu.router)
    
    # Лениво запускаем базу данных до старта бота
    await db.connect(DATABASE_URL)
    
    logging.info("Бот MIFL STAKE успешно запущен!")
    
    try:
        # Запуск прослушки Telegram
        await dp.start_polling(bot)
    finally:
        # Корректное закрытие базы при выключении
        if db.pool:
            await db.pool.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
