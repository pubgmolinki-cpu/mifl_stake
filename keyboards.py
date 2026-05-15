from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📋 Матчи"), KeyboardButton(text="💰 Мои ставки")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🏆 Топ-10")],
        [KeyboardButton(text="👥 Рефералка"), KeyboardButton(text="🎁 Бонус")],
        [KeyboardButton(text="🎰 Экспресс"), KeyboardButton(text="🎲 Интерактивные ставки")]
    ], resize_keyboard=True)

def match_outcome_keyboard(match_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="П1", callback_data=f"bet_{match_id}_p1"),
         InlineKeyboardButton(text="Х", callback_data=f"bet_{match_id}_x"),
         InlineKeyboardButton(text="П2", callback_data=f"bet_{match_id}_p2")],
        [InlineKeyboardButton(text="ТБ 2.5", callback_data=f"bet_{match_id}_tb"),
         InlineKeyboardButton(text="ТМ 2.5", callback_data=f"bet_{match_id}_tm")],
        [InlineKeyboardButton(text="ОЗ Да", callback_data=f"bet_{match_id}_ozy"),
         InlineKeyboardButton(text="ОЗ Нет", callback_data=f"bet_{match_id}_ozn")]
    ])
