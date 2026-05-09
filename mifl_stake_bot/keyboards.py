from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton
)

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⚽ Матчи")],
        [KeyboardButton(text="🎟️ Мои Ставки")],
        [KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="🎰 Экспресс")],
        [KeyboardButton(text="🗒️ Ивентовые Ставки")]
    ],
    resize_keyboard=True
)
