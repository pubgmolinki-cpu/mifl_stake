from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from database import db

# Создаем роутер, который мы подключили в main.py
router = Router()

def get_main_menu():
    """Функция для создания главного меню с кнопками"""
    kb = [
        [KeyboardButton(text="⚽ Матчи"), KeyboardButton(text="🎰 Экспресс")],
        [KeyboardButton(text="🎟️ Мои Ставки"), KeyboardButton(text="🗒️ Ивентовые Ставки")],
        [KeyboardButton(text="👤 Профиль")]
    ]
    # resize_keyboard=True делает кнопки компактными
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    # Добавляем пользователя в базу (общий баланс с MIFL CARDS)
    await db.add_user_if_not_exists(
        user_id=message.from_user.id, 
        username=message.from_user.username
    )
    
    welcome_text = (
        "Добро пожаловать в <b>MIFL STAKE</b>! 🎲\n\n"
        "Здесь ты можешь ставить на матчи, собирать экспрессы и следить за ивентами.\n"
        "Твой баланс полностью синхронизирован с MIFL CARDS.\n\n"
        "Выбери нужный раздел меню ниже:"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_menu(), parse_mode="HTML")

# --- ОБРАБОТЧИКИ КНОПОК МЕНЮ ---

@router.message(F.text == "⚽ Матчи")
async def show_matches(message: Message):
    """Обработка кнопки Матчи"""
    await message.answer(
        "⚽ <b>Список доступных матчей:</b>\n\n"
        "На данный момент активных матчей в линии нет.\n"
        "Скоро наш ИИ-аналитик добавит новые события!", 
        parse_mode="HTML"
    )

@router.message(F.text == "🎰 Экспресс")
async def show_express(message: Message):
    """Обработка кнопки Экспресс"""
    await message.answer(
        "🎰 <b>Ваш экспресс:</b>\n\n"
        "Вы еще не выбрали ни одного исхода.\n"
        "Чтобы собрать экспресс, выберите несколько событий в разделе «Матчи».", 
        parse_mode="HTML"
    )

@router.message(F.text == "🎟️ Мои Ставки")
async def my_bets(message: Message):
    """Обработка кнопки Мои Ставки"""
    await message.answer(
        "🎟️ <b>Ваша история ставок:</b>\n\n"
        "У вас пока нет активных ставок.\n"
        "Пора сделать первый прогноз!", 
        parse_mode="HTML"
    )

@router.message(F.text == "🗒️ Ивентовые Ставки")
async def event_bets(message: Message):
    """Обработка кнопки Ивентовые Ставки"""
    await message.answer(
        "🗒️ <b>Ивентовые события:</b>\n\n"
        "Здесь будут появляться уникальные ставки на турниры и спец-события MIFL.\n"
        "Следите за обновлениями!", 
        parse_mode="HTML"
    )

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    """Обработка кнопки Профиль (вывод баланса из общей БД)"""
    async with db.pool.acquire() as conn:
        balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", message.from_user.id)
    
    # Если баланса нет в БД (что вряд ли, но на всякий случай)
    if balance is None:
        balance = 0.0
        
    await message.answer(
        f"👤 <b>Твой профиль</b>\n\n"
        f"💰 Баланс: <b>{balance}</b> монет\n"
        f"🤝 Статус: Игрок MIFL", 
        parse_mode="HTML"
    )
