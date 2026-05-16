import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from database import db
from handlers import user, admin

logging.basicConfig(level=logging.INFO)

async def main():
    # 1. Запуск и проверка таблиц БД
    await db.connect()

    # 2. Инициализация бота
    bot_token = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА_СЮДА")
    bot = Bot(token=bot_token)
    dp = Dispatcher()

    # 3. Подключение модулей хендлеров
    dp.include_router(admin.router)
    dp.include_router(user.router)

    # Главное меню команд (кнопки снизу) при первом запуске /start
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        kb = [
            [types.KeyboardButton(text="📋 Матчи"), types.KeyboardButton(text="🎭 Интерактивные Ставки")],
            [types.KeyboardButton(text="👤 Профиль"), types.KeyboardButton(text="📊 Мои Ставки"), types.KeyboardButton(text="🎁 Бонус")]
        ]
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        await message.answer("👋 Добро пожаловать в симулятор ставок лиг **FTCL и MIFL**!\nВыберите интересующий раздел в меню ниже:", reply_markup=keyboard)

    # 4. Старт Long Polling
    logging.info("Бот успешно запущен в режиме Long Polling!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    from aiogram.filters import Command # локальный импорт для команды старт
    asyncio.run(main())
