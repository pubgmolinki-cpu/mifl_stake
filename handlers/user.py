import json
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db

router = Router()
logger = logging.getLogger(__name__)

# ==========================================
# 1. ОСНОВНОЙ ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ
# ==========================================
@router.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", message.from_user.id)
        # Если юзера почему-то нет в БД, создаем его базовый профиль
        if not user:
            await conn.execute("INSERT INTO users (user_id, balance) VALUES ($1, 1000.0)", message.from_user.id)
            balance = 1000.0
        else:
            balance = user['balance']
            
        bets_count = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1", message.from_user.id)
        
    await message.answer(
        f"👤 Ваш профиль FTCL/MIFL\n\n"
        f"🆔 Твой ID: `{message.from_user.id}`\n"
        f"💰 Игровой баланс: `{round(balance, 1)}` ⭐️\n"
        f"📊 Всего сделано ставок: `{bets_count}`",
        parse_mode="Markdown"
    )


# ==========================================
# 2. ЕЖЕДНЕВНЫЙ БОНУС К БАЛАНСУ
# ==========================================
@router.message(F.text == "🎁 Бонус")
async def get_bonus(message: types.Message):
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT last_bonus FROM users WHERE user_id = $1", message.from_user.id)
        
        now = datetime.now()
        # Проверяем, прошло ли 24 часа с момента последнего получения
        if user and user['last_bonus'] and (now - user['last_bonus']) < timedelta(hours=24):
            time_passed = now - user['last_bonus']
            seconds_left = 86400 - time_passed.total_seconds()
            hours_left = int(seconds_left // 3600)
            minutes_left = int((seconds_left % 3600) // 60)
            
            await message.answer(f"⏳ Вы уже забирали бонус! Приходите снова через: {hours_left}ч. {minutes_left}мин.")
            return

        bonus_amount = 500.0  # Сумма ежедневного бонуса
        await conn.execute(
            "UPDATE users SET balance = balance + $1, last_bonus = $2 WHERE user_id = $3", 
            bonus_amount, now, message.from_user.id
        )
        
    await message.answer(f"🎉 Отлично! Вам начислено: **+{round(bonus_amount, 1)} ⭐️**")


# ==========================================
# 3. ИСТОРИЯ ПОСЛЕДНИХ СТАВОК ИГРОКА
# ==========================================
@router.message(F.text == "📊 Мои Ставки")
async def my_bets(message: types.Message):
    async with db.pool.acquire() as conn:
        bets = await conn.fetch("SELECT id, amount, coef, status FROM bets WHERE user_id = $1 ORDER BY id DESC LIMIT 5", message.from_user.id)
    
    if not bets:
        return await message.answer("ℹ️ У вас пока нет открытых или завершенных ставок.")

    text = "📝 **Ваши последние 5 купонов:**\n\n"
    for b in bets:
        if b['status'] == 'won':
            status_emoji = "🟢 Выигрыш"
        elif b['status'] == 'lost':
            status_emoji = "🔴 Проигрыш"
        else:
            status_emoji = "⏳ В игре"
            
        text += f"{status_emoji} | Купон #{b['id']}\nСумма: `{round(b['amount'], 1)}` ⭐️ | Кэф: `{round(b['coef'], 1)}`\n"
        text += "—" * 15 + "\n"
        
    await message.answer(text, parse_mode="Markdown")


# ==========================================
# 4. ИНЛАЙН ВЫБОР МАТЧЕЙ (ЛИНИЯ)
# ==========================================
@router.message(F.text == "📋 Матчи")
async def show_matches_inline(message: types.Message):
    async with db.pool.acquire() as conn:
        matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active' ORDER BY id DESC")
    
    if not matches:
        return await message.answer("😔 На данный момент нет активных матчей для ставок.")

    # Строим клавиатуру: каждая кнопка — отдельный матч
    builder = []
    for m in matches:
        builder.append([InlineKeyboardButton(text=f"⚽️ {m['title']}", callback_data=f"match_{m['id']}")])
        
    kb = InlineKeyboardMarkup(inline_keyboard=builder)
    await message.answer("👇 Выберите интересующий матч из списка:", reply_markup=kb, parse_mode="Markdown")


# ==========================================
# 5. ИНТЕРАКТИВНЫЕ СТАВКИ (ДОЛГОСРОЧНЫЕ СОБЫТИЯ)
# ==========================================
@router.message(F.text == "🎭 Интерактивные Ставки")
async def show_interactive(message: types.Message):
    async with db.pool.acquire() as conn:
        events = await conn.fetch("SELECT id, title, options FROM interactive_bets WHERE status = 'active' ORDER BY id DESC")
        
    if not events:
        return await message.answer("ℹ️ Сейчас нет активных интерактивных событий.")

    for event in events:
        options = json.loads(event['options'])
        text = f"🏆 АКТУАЛЬНЫЙ ИНТЕРАКТИВ:\n🔥 `{event['title']}`\n\n"
        text += "📈 Доступные котировки на исходы:\n"
        
        builder = []
        for opt_name, coef in options.items():
            # Округляем коэффициент интерактива до 1 знака
            rounded_coef = round(float(coef), 1)
            text += f"• {opt_name} — `{rounded_coef}`\n"
            
            # Инлайн кнопка для мгновенного выбора ставки игроком
            builder.append([InlineKeyboardButton(
                text=f"{opt_name} ({rounded_coef})", 
                callback_data=f"ib_{event['id']}_{opt_name}"
            )])
            
        kb = InlineKeyboardMarkup(inline_keyboard=builder)
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
