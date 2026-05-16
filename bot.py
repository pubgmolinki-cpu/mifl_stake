import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from database import db
from handlers import user, admin
from aiohttp import web  # Импортируем для работы с портом Render

logging.basicConfig(level=logging.INFO)

# ========================================================
# ФЕЙКОВЫЙ ВЕБ-СЕРВЕР ДЛЯ ПРОХОЖДЕНИЯ ХЕЛСЧЕКОВ RENDER
# ========================================================
async def handle_health_check(request):
    """Отвечает Render, что с ботом всё в порядке"""
    return web.Response(text="Бот FTCL/MIFL успешно работает!", status=200)

async def start_render_port_listener():
    """Запускает веб-сервер на порту, который требует Render"""
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render сам передает нужный порт в переменную окружения PORT
    port = int(os.getenv("PORT", 8080)) 
    site = web.TCPSite(runner, "0.0.0.0", port)
    
    await site.start()
    logging.info(f"Слушатель порта для Render успешно запущен на 0.0.0.0:{port}")


# ========================================================
# ГЛАВНАЯ ФУНКЦИЯ ЗАПУСКА БОТА
# ========================================================
async def main():
    # 1. Запуск и автоматическая проверка таблиц БД
    await db.connect()

    # 2. Инициализация бота (берем токен из env или подставляем строку)
    bot_token = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА_СЮДА")
    bot = Bot(token=bot_token)
    dp = Dispatcher()

    # 3. Подключение роутеров с логикой
    dp.include_router(admin.router)
    dp.include_router(user.router)

    # Стартовая команда для создания нижнего меню кнопок
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        kb = [
            [types.KeyboardButton(text="📋 Матчи"), types.KeyboardButton(text="🎭 Интерактивные Ставки")],
            [types.KeyboardButton(text="👤 Профиль"), types.KeyboardButton(text="📊 Мои Ставки"), types.KeyboardButton(text="🎁 Бонус")]
        ]
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        await message.answer(
            "👋 Привет! Добро пожаловать в симулятор ставок лиг **FTCL и MIFL**!\n"
            "Используй меню ниже для навигации:", 
            reply_markup=keyboard
        )

    # 4. Запускаем веб-сервер для порта Render в фоновом таске
    asyncio.create_task(start_render_port_listener())

    # 5. Старт поллинга aiogram
    logging.info("Бот запущен в режиме Long Polling!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
