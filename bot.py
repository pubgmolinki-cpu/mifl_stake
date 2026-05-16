import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from database import db
from handlers import user, admin
from aiohttp import web

logging.basicConfig(level=logging.INFO)

async def handle_health_check(request):
    return web.Response(text="Бот FTCL BET успешно работает!", status=200)

async def start_render_port_listener():
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080)) 
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Слушатель порта для Render запущен на 0.0.0.0:{port}")

async def main():
    await db.connect()

    bot_token = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА_СЮДА")
    bot = Bot(token=bot_token)
    dp = Dispatcher()

    dp.include_router(admin.router)
    dp.include_router(user.router)

    # ОБРАБОТКА КОМАНДЫ START С РЕФЕРАЛЬНОЙ СИСТЕМОЙ
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        args = message.text.split()
        referrer_id = None
        
        # Проверяем, зашел ли юзер по реф-ссылке
        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                referrer_id = int(args[1].split("_")[1])
            except ValueError:
                pass

        async with db.pool.acquire() as conn:
            async with conn.transaction():
                exist_user = await conn.fetchrow("SELECT user_id FROM users WHERE user_id = $1", message.from_user.id)
                if not exist_user:
                    # Новый пользователь
                    ref_to_save = referrer_id if referrer_id and referrer_id != message.from_user.id else None
                    await conn.execute("INSERT INTO users (user_id, balance, referred_by) VALUES ($1, 1000.0, $2)", message.from_user.id, ref_to_save)
                    
                    if ref_to_save:
                        # Начисляем создателю ссылки 250 звёзд
                        await conn.execute("UPDATE users SET balance = balance + 250.0 WHERE user_id = $1", ref_to_save)
                        try:
                            await bot.send_message(ref_to_save, f"🎉 По вашей ссылке зарегистрировался новый игрок! Вам начислено +250.0 ⭐️")
                        except Exception:
                            pass

        # Главное меню (с добавленными новыми кнопками, без звёздочек в тексте)
        kb = [
            [types.KeyboardButton(text="📋 Матчи"), types.KeyboardButton(text="🚀 Экспресс")],
            [types.KeyboardButton(text="👤 Профиль"), types.KeyboardButton(text="🏆 Топ 10"), types.KeyboardButton(text="👥 Рефералка")],
            [types.KeyboardButton(text="🎁 Бонус"), types.KeyboardButton(text="📊 Мои Ставки"), types.KeyboardButton(text="🎟 Промокоды")]
        ]
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        await message.answer(
            "👋 Привет! Добро пожаловать в симулятор ставок FTCL 3 и 4!\n"
            "Выберите интересующий раздел в меню ниже:", 
            reply_markup=keyboard
        )

    asyncio.create_task(start_render_port_listener())
    await bot.delete_webhook(drop_pending_updates=True)
    
    logging.info("Бот запущен в режиме Long Polling!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
