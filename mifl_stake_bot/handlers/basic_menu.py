from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from database import db

router = Router()

def get_main_menu():
    kb = [
        [KeyboardButton(text="⚽ Матчи"), KeyboardButton(text="🎰 Экспресс")],
        [KeyboardButton(text="🎟️ Мои Ставки"), KeyboardButton(text="🗒️ Ивентовые Ставки")],
        [KeyboardButton(text="👤 Профиль")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@router.message(CommandStart())
async def cmd_start(message: Message):
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

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    async with db.pool.acquire() as conn:
        balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", message.from_user.id)
    
    # Защита от ошибки, если юзер как-то нажал кнопку до старта
    if balance is None:
        balance = 0.0
        
    await message.answer(f"👤 <b>Твой профиль</b>\n\n💰 Баланс: <b>{balance}</b> монет", parse_mode="HTML")
