import json
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db

router = Router()

# Состояние для оформления ставки
class UserBetStates(StatesGroup):
    waiting_for_amount = State()

# ==========================================
# 1. ГЛАВНЫЙ ПРОФИЛЬ
# ==========================================
@router.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", message.from_user.id)
        if not user:
            await conn.execute("INSERT INTO users (user_id, balance) VALUES ($1, 1000.0)", message.from_user.id)
            balance = 1000.0
        else:
            balance = user['balance']
            
        bets_count = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1", message.from_user.id)
        
    await message.answer(
        f"👤 **Ваш профиль FTCL/MIFL**\n\n"
        f"🆔 Твой ID: `{message.from_user.id}`\n"
        f"💰 Игровой баланс: `{round(balance, 1)}` ⭐️\n"
        f"📊 Всего сделано ставок: `{bets_count}`",
        parse_mode="Markdown"
    )

# ==========================================
# 2. ЕЖЕДНЕВНЫЙ БОНУС
# ==========================================
@router.message(F.text == "🎁 Бонус")
async def get_bonus(message: types.Message):
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT last_bonus FROM users WHERE user_id = $1", message.from_user.id)
        
        now = datetime.now()
        if user and user['last_bonus'] and (now - user['last_bonus']) < timedelta(hours=24):
            time_passed = now - user['last_bonus']
            seconds_left = 86400 - time_passed.total_seconds()
            return await message.answer(f"⏳ Бонус уже получен! Приходите через: **{int(seconds_left // 3600)}ч. {int((seconds_left % 3600) // 60)}мин.**")

        bonus_amount = 500.0
        await conn.execute("UPDATE users SET balance = balance + $1, last_bonus = $2 WHERE user_id = $3", bonus_amount, now, message.from_user.id)
        
    await message.answer(f"🎉 Вам начислено: **+{round(bonus_amount, 1)} ⭐️**")

# ==========================================
# 3. ИСТОРИЯ СТАВОК
# ==========================================
@router.message(F.text == "📊 Мои Ставки")
async def my_bets(message: types.Message):
    async with db.pool.acquire() as conn:
        bets = await conn.fetch("SELECT id, amount, coef, status FROM bets WHERE user_id = $1 ORDER BY id DESC LIMIT 5", message.from_user.id)
    
    if not bets:
        return await message.answer("ℹ️ У вас пока нет ставок.")

    text = "📝 **Последние 5 купонов:**\n\n"
    for b in bets:
        status_emoji = "🟢 Выигрыш" if b['status'] == 'won' else "🔴 Проигрыш" if b['status'] == 'lost' else "⏳ В игре"
        text += f"{status_emoji} | Купон #{b['id']}\nСумма: `{round(b['amount'], 1)}` ⭐️ | Кэф: `{round(b['coef'], 1)}`\n"
        text += "—" * 15 + "\n"
        
    await message.answer(text, parse_mode="Markdown")

# ==========================================
# 4. ЛИНИЯ МАТЧЕЙ И ИНЛАЙН СТАВКИ
# ==========================================
@router.message(F.text == "📋 Матчи")
async def show_matches_inline(message: types.Message):
    async with db.pool.acquire() as conn:
        matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active' ORDER BY id DESC")
    
    if not matches:
        return await message.answer("😔 На данный момент нет активных матчей.")

    builder = []
    for m in matches:
        builder.append([InlineKeyboardButton(text=f"⚽️ {m['title']}", callback_data=f"match_{m['id']}")])
        
    kb = InlineKeyboardMarkup(inline_keyboard=builder)
    await message.answer("👇 **Выберите матч для ставки:**", reply_markup=kb, parse_mode="Markdown")

# Открытие маркетов выбранного матча
@router.callback_query(F.data.startswith("match_"))
async def handle_match_choice(callback: types.CallbackQuery):
    match_id = int(callback.data.split("_")[1])
    
    async with db.pool.acquire() as conn:
        m = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", match_id)
        
    if not m or m['status'] != 'active':
        return await callback.answer("❌ Матч уже завершен или не найден.")

    text = f"🏆 **{m['title']}**\n\nВыберите исход для одиночной ставки:"
    
    # Кнопки с округленными до десятых кэфами
    kb = [
        [
            InlineKeyboardButton(text=f"П1 ({round(m['coef_p1'], 1)})", callback_data=f"bet_{match_id}_p1_{round(m['coef_p1'], 1)}"),
            InlineKeyboardButton(text=f"Х ({round(m['coef_x'], 1)})", callback_data=f"bet_{match_id}_x_{round(m['coef_x'], 1)}"),
            InlineKeyboardButton(text=f"П2 ({round(m['coef_p2'], 1)})", callback_data=f"bet_{match_id}_p2_{round(m['coef_p2'], 1)}")
        ],
        [
            InlineKeyboardButton(text=f"ТБ 2.5 ({round(m['coef_tb'], 1)})", callback_data=f"bet_{match_id}_tb_{round(m['coef_tb'], 1)}"),
            InlineKeyboardButton(text=f"ТМ 2.5 ({round(m['coef_tm'], 1)})", callback_data=f"bet_{match_id}_tm_{round(m['coef_tm'], 1)}")
        ],
        [
            InlineKeyboardButton(text=f"ОЗ Да ({round(m['coef_oz_yes'], 1)})", callback_data=f"bet_{match_id}_oz_yes_{round(m['coef_oz_yes'], 1)}"),
            InlineKeyboardButton(text=f"ОЗ Нет ({round(m['coef_oz_no'], 1)})", callback_data=f"bet_{match_id}_oz_no_{round(m['coef_oz_no'], 1)}")
        ]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# Переход к вводу суммы
@router.callback_query(F.data.startswith("bet_"))
async def process_bet_selection(callback: types.CallbackQuery, state: FSMContext):
    _, match_id, outcome, coef = callback.data.split("_", 3)
    
    await state.update_data(match_id=int(match_id), outcome=outcome, coef=float(coef))
    await callback.message.answer(f"📊 Вы выбрали исход **{outcome.upper()}** с коэффициентом `{coef}`.\n💰 Введите сумму ставки в чат:")
    await state.set_state(UserBetStates.waiting_for_amount)
    await callback.answer()

# Прием суммы ставки и запись в БД
@router.message(UserBetStates.waiting_for_amount)
async def accept_bet_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Сумма ставки должна быть целым числом!")
        
    amount = float(message.text)
    if amount <= 0:
        return await message.answer("❌ Сумма должна быть больше нуля!")

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", message.from_user.id)
        if not user or user['balance'] < amount:
            await state.clear()
            return await message.answer("❌ Недостаточно средств на балансе!")

        data = await state.get_data()
        
        # Списываем баланс и создаем купон
        await conn.execute("UPDATE users SET balance = balance - $1 WHERE user_id = $2", amount, message.from_user.id)
        await conn.execute(
            "INSERT INTO bets (user_id, match_ids, outcomes, coef, amount, status) VALUES ($1, $2, $3, $4, $5, 'pending')",
            message.from_user.id, [data['match_id']], [data['outcome']], data['coef'], amount
        )
        
    await message.answer(f"✅ **Ставка принята!**\n📋 Исход: {data['outcome'].upper()} | Кэф: {data['coef']}\n💵 Сумма: {amount} ⭐️")
    await state.clear()

# ==========================================
# 5. ИНТЕРАКТИВНЫЕ СТАВКИ
# ==========================================
@router.message(F.text == "🎭 Интерактивные Ставки")
async def show_interactive(message: types.Message):
    async with db.pool.acquire() as conn:
        events = await conn.fetch("SELECT id, title, options FROM interactive_bets WHERE status = 'active' ORDER BY id DESC")
        
    if not events:
        return await message.answer("ℹ️ Сейчас нет активных интерактивных событий.")

    for event in events:
        options = json.loads(event['options'])
        text = f"🏆 **АКТУАЛЬНЫЙ ИНТЕРАКТИВ:**\n🔥 `{event['title']}`\n\n📈 **Котировки:**\n"
        
        builder = []
        for opt_name, coef in options.items():
            rounded_coef = round(float(coef), 1)
            text += f"• {opt_name} — `{rounded_coef}`\n"
            builder.append([InlineKeyboardButton(text=f"{opt_name} ({rounded_coef})", callback_data=f"ib_{event['id']}_{opt_name}")])
            
        kb = InlineKeyboardMarkup(inline_keyboard=builder)
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
