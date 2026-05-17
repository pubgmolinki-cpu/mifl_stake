from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from database import db
import json
import random
from datetime import datetime, timedelta

router = Router()

# Список обязательных каналов
CHANNELS = [
    {"username": "@ftclbet34", "url": "https://t.me/ftclbet34", "name": "📢 Канал 1"},
    {"username": "@mneniefutshera", "url": "https://t.me/mneniefutshera", "name": "📢 Канал 2"}
]

class BetStates(StatesGroup):
    waiting_for_amount = State()

class ExpressStates(StatesGroup):
    selecting_matches = State()   
    selecting_outcomes = State()  
    waiting_for_amount = State()  

class PromoStates(StatesGroup):
    waiting_for_code = State()

async def check_bets_lock(conn) -> bool:
    await conn.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)")
    status = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'bets_locked'")
    return status == 'true'

async def check_referral_reward(bot, user_id: int):
    """Проверяет, является ли пользователь чьим-то рефералом, и выдает награду, если он подписался."""
    try:
        async with db.pool.acquire() as conn:
            ref = await conn.fetchrow("SELECT referrer_id FROM referrals WHERE referred_id = $1 AND status = 'pending'", user_id)
            if ref:
                referrer_id = ref['referrer_id']
                
                # Отмечаем как выполненный и начисляем баланс
                await conn.execute("UPDATE referrals SET status = 'completed' WHERE referred_id = $1", user_id)
                await conn.execute("UPDATE users SET balance = balance + 250 WHERE user_id = $1", referrer_id)
                
                # Уведомляем пригласившего
                try:
                    chat = await bot.get_chat(user_id)
                    ref_name = f"@{chat.username}" if chat.username else chat.first_name
                    await bot.send_message(
                        referrer_id,
                        f"Ваш друг ({ref_name}) подписался на нужные каналы ✅\nМы зачислили вам 250 ⭐"
                    )
                except Exception:
                    pass
    except Exception as e:
        print(f"Ошибка реферальной системы: {e}")

async def is_subscribed(bot, user_id: int) -> bool:
    """Проверяет подписку пользователя на все каналы."""
    try:
        for ch in CHANNELS:
            member = await bot.get_chat_member(chat_id=ch["username"], user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        
        # Если дошли сюда — подписан на все. Проверяем и выдаем реферальный бонус!
        await check_referral_reward(bot, user_id)
        return True
    except Exception:
        return False

def sub_keyboard():
    """Возвращает клавиатуру со списком каналов и кнопкой проверки."""
    builder = InlineKeyboardBuilder()
    for ch in CHANNELS:
        builder.button(text=ch["name"], url=ch["url"])
    builder.button(text="✅ Я подписался!", callback_data="check_sub")
    builder.adjust(1)
    return builder.as_markup()

@router.callback_query(F.data == "check_sub")
async def process_sub_check(callback: CallbackQuery):
    if await is_subscribed(callback.bot, callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("✅ Спасибо за подписку! Теперь вам доступен весь функционал бота.")
    else:
        await callback.answer("❌ Вы всё ещё не подписаны на все обязательные каналы!", show_alert=True)

# =====================================================================
# 0. СТАРТ И РЕФЕРАЛКА (НОВОЕ)
# =====================================================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    text_parts = message.text.split()
    
    async with db.pool.acquire() as conn:
        # Создаем таблицу для рефералов, если её нет
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                referred_id BIGINT PRIMARY KEY,
                referrer_id BIGINT,
                status TEXT
            )
        ''')
        
        # Обработка реферальной ссылки: /start <referrer_id>
        if len(text_parts) > 1 and text_parts[1].isdigit():
            referrer_id = int(text_parts[1])
            if referrer_id != user_id:
                exists = await conn.fetchval("SELECT 1 FROM referrals WHERE referred_id = $1", user_id)
                if not exists:
                    # Записываем как "ожидание подписки"
                    await conn.execute("INSERT INTO referrals (referred_id, referrer_id, status) VALUES ($1, $2, 'pending')", user_id, referrer_id)
                    
                    ref_user = message.from_user.username
                    ref_name = f"@{ref_user}" if ref_user else message.from_user.first_name
                    
                    try:
                        await message.bot.send_message(
                            referrer_id,
                            f"Ваш друг ({ref_name}) перешёл по ссылке! 🔥\nЖдём когда он подпишется на обязательные каналы и сразу начислим вам 250 ⭐"
                        )
                    except Exception:
                        pass
    
    if not await is_subscribed(message.bot, user_id):
        await message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())
    else:
        await message.answer("✅ Добро пожаловать в FTCL BET 34! Используйте меню бота для ставок.")

# =====================================================================
# 1. МАТЧИ И СТАВКИ
# =====================================================================

@router.message(F.text == "📋 Матчи")
async def show_matches(message: Message):
    if not await is_subscribed(message.bot, message.from_user.id):
        return await message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    builder = InlineKeyboardBuilder()
    async with db.pool.acquire() as conn:
        active_matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    
    if not active_matches:
        return await message.answer("🎰 На данный момент нет активных матчей.")
        
    text = "Выберите матч, на который готовы поставить! 👇"
    for m in active_matches:
        builder.button(text=f"{m['title']}", callback_data=f"select_match_{m['id']}")
    
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("select_match_"))
async def step_match_outcomes(callback: CallbackQuery, state: FSMContext):
    if not await is_subscribed(callback.bot, callback.from_user.id):
        return await callback.message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    m_id = int(callback.data.split("_")[2])
    
    async with db.pool.acquire() as conn:
        if await check_bets_lock(conn):
            return await callback.answer("❌ Ставки временно заморожены администрацией!", show_alert=True)
            
        match_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", m_id)
        
    if not match_data:
        return await callback.answer("❌ Матч не найден.", show_alert=True)
        
    m_dict = dict(match_data)
    await state.update_data(match_id=m_id)
    
    c_p1 = round(float(m_dict.get("coef_p1") or 2.0), 1)
    c_x = round(float(m_dict.get("coef_x") or 2.0), 1)
    c_p2 = round(float(m_dict.get("coef_p2") or 2.0), 1)
    c_tb = round(float(m_dict.get("coef_tb") or 2.0), 1)
    c_tm = round(float(m_dict.get("coef_tm") or 2.0), 1)
    c_oz = round(float(m_dict.get("coef_oz_yes") or m_dict.get("coef_oz") or 2.0), 1)

    builder = InlineKeyboardBuilder()
    builder.button(text=f"П1 ({c_p1})", callback_data=f"bet_p1_{m_id}")
    builder.button(text=f"X ({c_x})", callback_data=f"bet_x_{m_id}")
    builder.button(text=f"П2 ({c_p2})", callback_data=f"bet_p2_{m_id}")
    builder.button(text=f"ТБ 2.5 ({c_tb})", callback_data=f"bet_tb2.5_{m_id}")
    builder.button(text=f"ТМ 2.5 ({c_tm})", callback_data=f"bet_tm2.5_{m_id}")
    builder.button(text=f"ОЗ ({c_oz})", callback_data=f"bet_oz_{m_id}")
    
    builder.adjust(3, 3)
    await callback.message.answer(f"📊 Выберите исход для одиночной ставки на матч:\n{m_dict['title']}", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("bet_"))
async def select_bet_outcome(callback: CallbackQuery, state: FSMContext):
    if not await is_subscribed(callback.bot, callback.from_user.id):
        return await callback.message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    async with db.pool.acquire() as conn:
        if await check_bets_lock(conn):
            return await callback.answer("❌ Ошибка: прием ставок закрыт!", show_alert=True)

    parts = callback.data.split("_")
    chosen_outcome = parts[1]
    match_id = int(parts[2])
    
    await state.update_data(outcome_choice=chosen_outcome, match_id=match_id)
    await callback.message.answer(f"📊 Вы выбрали исход {chosen_outcome.upper()}.\n💰 Введите сумму ставки в чат:")
    await state.set_state(BetStates.waiting_for_amount)
    await callback.answer()


@router.message(BetStates.waiting_for_amount)
async def accept_bet_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Пожалуйста, введите сумму ставки цифрами.")

    bet_amount = float(message.text)
    user_id = message.from_user.id
    
    state_data = await state.get_data()
    outcome_choice = state_data.get('outcome_choice') 
    match_id = state_data.get('match_id')
    
    if not outcome_choice or not match_id:
        await message.answer("❌ Ошибка: сессия потеряна. Начните заново.")
        await state.clear()
        return

    try:
        async with db.pool.acquire() as conn:
            if await check_bets_lock(conn):
                await state.clear()
                return await message.answer("❌ Администратор закрыл ставки.")

            balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
            if balance < bet_amount:
                return await message.answer("❌ Недостаточно средств на балансе!")

            match_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", int(match_id))
            if not match_data:
                return await message.answer("❌ Матч больше не существует.")

            match_dict = dict(match_data)
            col_name = f"coef_{outcome_choice}"
            if outcome_choice == "tb2.5": col_name = "coef_tb"
            elif outcome_choice == "tm2.5": col_name = "coef_tm"
            elif outcome_choice == "oz": col_name = "coef_oz_yes" if "coef_oz_yes" in match_dict else "coef_oz"
            
            coef = round(float(match_dict.get(col_name) or 2.0), 1)

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bets (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    match_ids BIGINT[],
                    outcomes TEXT[],
                    bet_type TEXT,
                    amount NUMERIC,
                    coef NUMERIC,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')

            try:
                await conn.execute("ALTER TABLE bets ALTER COLUMN bet_type DROP NOT NULL;")
                await conn.execute("ALTER TABLE bets ALTER COLUMN bet_type SET DEFAULT 'single';")
            except Exception:
                pass

            await conn.execute(
                """
                INSERT INTO bets (user_id, match_ids, outcomes, bet_type, amount, coef, status) 
                VALUES ($1, $2, $3, $4, $5, $6, 'pending')
                """,
                user_id, [int(match_id)], [str(outcome_choice)], 'single', float(bet_amount), float(coef)
            )
            await conn.execute("UPDATE users SET balance = balance - $1 WHERE user_id = $2", float(bet_amount), user_id)
            
        await message.answer(f"✅ Ставка успешно принята!\n🎰 Сумма: {bet_amount} | Кэф: {coef}")
        await state.clear()

    except Exception as e:
        await message.answer(f"❌ Ошибка БД при ставке: {e}")
        await state.clear()

# =====================================================================
# 2. ЭКСПРЕССЫ
# =====================================================================

@router.message(F.text == "🚀 Экспресс")
async def start_express(message: Message, state: FSMContext):
    if not await is_subscribed(message.bot, message.from_user.id):
        return await message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    async with db.pool.acquire() as conn:
        if await check_bets_lock(conn):
            return await message.answer("❌ Экспрессы недоступны. Ставки заморожены.")

    await state.update_data(express_match_ids=[], express_legs=[])
    builder = InlineKeyboardBuilder()
    async with db.pool.acquire() as conn:
        active_matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    
    if not active_matches:
        return await message.answer("ℹ️ Сейчас нет активных матчей.")

    for match in active_matches:
        builder.button(text=f"{match['title']}", callback_data=f"exp_toggle_{match['id']}")
    builder.button(text="✅ Подтвердить выбор", callback_data="exp_confirm_matches")
    builder.adjust(1)
    
    await message.answer("⚽ Выберите матчи для Экспресса:", reply_markup=builder.as_markup())
    await state.set_state(ExpressStates.selecting_matches)

@router.callback_query(ExpressStates.selecting_matches, F.data.startswith("exp_toggle_"))
async def toggle_express_match(callback: CallbackQuery, state: FSMContext):
    if not await is_subscribed(callback.bot, callback.from_user.id):
        return await callback.message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    match_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected_ids = data.get("express_match_ids", [])
    
    if match_id in selected_ids:
        selected_ids.remove(match_id)
        await callback.answer("❌ Матч удален")
    else:
        selected_ids.append(match_id)
        await callback.answer("✅ Матч добавлен")
    await state.update_data(express_match_ids=selected_ids)

@router.callback_query(ExpressStates.selecting_matches, F.data == "exp_confirm_matches")
async def confirm_matches_for_express(callback: CallbackQuery, state: FSMContext):
    if not await is_subscribed(callback.bot, callback.from_user.id):
        return await callback.message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    data = await state.get_data()
    selected_ids = data.get("express_match_ids", [])
    if len(selected_ids) < 2:
        return await callback.answer("❌ Нужно выбрать минимум 2 матча!", show_alert=True)
        
    await state.update_data(current_index=0)
    first_match_id = selected_ids[0]
    
    async with db.pool.acquire() as conn:
        match_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", first_match_id)
        
    if not match_data:
        return await callback.answer("❌ Матч не найден.", show_alert=True)
        
    m_dict = dict(match_data)
    
    c_p1 = round(float(m_dict.get("coef_p1") or 2.0), 1)
    c_x = round(float(m_dict.get("coef_x") or 2.0), 1)
    c_p2 = round(float(m_dict.get("coef_p2") or 2.0), 1)
    c_tb = round(float(m_dict.get("coef_tb") or 2.0), 1)
    c_tm = round(float(m_dict.get("coef_tm") or 2.0), 1)
    c_oz = round(float(m_dict.get("coef_oz_yes") or m_dict.get("coef_oz") or 2.0), 1)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"П1 ({c_p1})", callback_data=f"exp_choice_p1_{first_match_id}")
    builder.button(text=f"X ({c_x})", callback_data=f"exp_choice_x_{first_match_id}")
    builder.button(text=f"П2 ({c_p2})", callback_data=f"exp_choice_p2_{first_match_id}")
    builder.button(text=f"ТБ 2.5 ({c_tb})", callback_data=f"exp_choice_tb2.5_{first_match_id}")
    builder.button(text=f"ТМ 2.5 ({c_tm})", callback_data=f"exp_choice_tm2.5_{first_match_id}")
    builder.button(text=f"ОЗ ({c_oz})", callback_data=f"exp_choice_oz_{first_match_id}")
    builder.adjust(3, 3)
    
    await callback.message.edit_text(f"📋 Шаг 1/{len(selected_ids)}: Выберите исход для матча\n{m_dict['title']}:", reply_markup=builder.as_markup())
    await state.set_state(ExpressStates.selecting_outcomes)

@router.callback_query(ExpressStates.selecting_outcomes, F.data.startswith("exp_choice_"))
async def process_express_outcome_step(callback: CallbackQuery, state: FSMContext):
    if not await is_subscribed(callback.bot, callback.from_user.id):
        return await callback.message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    parts = callback.data.split("_")
    outcome = parts[2]
    match_id = int(parts[3])
    
    data = await state.get_data()
    selected_ids = data.get("express_match_ids", [])
    express_legs = data.get("express_legs", [])
    current_index = data.get("current_index", 0)
    
    express_legs.append({"match_id": match_id, "outcome": outcome})
    current_index += 1
    await state.update_data(express_legs=express_legs, current_index=current_index)
    
    if current_index < len(selected_ids):
        next_match_id = selected_ids[current_index]
        
        async with db.pool.acquire() as conn:
            match_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", next_match_id)
            
        if not match_data:
            return await callback.answer("❌ Ошибка: матч не найден.", show_alert=True)
            
        m_dict = dict(match_data)
        
        c_p1 = round(float(m_dict.get("coef_p1") or 2.0), 1)
        c_x = round(float(m_dict.get("coef_x") or 2.0), 1)
        c_p2 = round(float(m_dict.get("coef_p2") or 2.0), 1)
        c_tb = round(float(m_dict.get("coef_tb") or 2.0), 1)
        c_tm = round(float(m_dict.get("coef_tm") or 2.0), 1)
        c_oz = round(float(m_dict.get("coef_oz_yes") or m_dict.get("coef_oz") or 2.0), 1)
        
        builder = InlineKeyboardBuilder()
        builder.button(text=f"П1 ({c_p1})", callback_data=f"exp_choice_p1_{next_match_id}")
        builder.button(text=f"X ({c_x})", callback_data=f"exp_choice_x_{next_match_id}")
        builder.button(text=f"П2 ({c_p2})", callback_data=f"exp_choice_p2_{next_match_id}")
        builder.button(text=f"ТБ 2.5 ({c_tb})", callback_data=f"exp_choice_tb2.5_{next_match_id}")
        builder.button(text=f"ТМ 2.5 ({c_tm})", callback_data=f"exp_choice_tm2.5_{next_match_id}")
        builder.button(text=f"ОЗ ({c_oz})", callback_data=f"exp_choice_oz_{next_match_id}")
        builder.adjust(3, 3)
        
        await callback.message.edit_text(f"📋 Шаг {current_index + 1}/{len(selected_ids)}: Выберите исход для матча\n{m_dict['title']}:", reply_markup=builder.as_markup())
    else:
        await callback.message.edit_text("💰 Все исходы выбраны! Введите сумму ставки на экспресс:")
        await state.set_state(ExpressStates.waiting_for_amount)
    await callback.answer()

@router.message(ExpressStates.waiting_for_amount)
async def accept_express_final_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Введите сумму цифрами.")
        
    final_amount = float(message.text)
    user_id = message.from_user.id
    data = await state.get_data()
    express_legs = data.get("express_legs", [])
    
    try:
        total_coef = 1.0
        async with db.pool.acquire() as conn:
            if await check_bets_lock(conn):
                await state.clear()
                return await message.answer("❌ Ставки закрыты администратором.")

            for leg in express_legs:
                m_id = leg['match_id']
                b_t = leg['outcome']
                m_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", m_id)
                if m_data:
                    m_dict = dict(m_data)
                    col = f"coef_{b_t}"
                    if b_t == "tb2.5": col = "coef_tb"
                    elif b_t == "tm2.5": col = "coef_tm"
                    elif b_t == "oz": col = "coef_oz_yes" if "coef_oz_yes" in m_dict else "coef_oz"
                    total_coef *= float(m_dict.get(col) or 1.0)
            
            total_coef = round(total_coef, 1)
            balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
            if balance < final_amount:
                return await message.answer("❌ Недостаточно баланса для экспресса!")

            m_ids = [int(leg['match_id']) for leg in express_legs]
            outcomes = [str(leg['outcome']) for leg in express_legs]
            
            await conn.execute(
                """
                INSERT INTO bets (user_id, match_ids, outcomes, bet_type, amount, coef, status) 
                VALUES ($1, $2, $3, $4, $5, $6, 'pending')
                """,
                user_id, m_ids, outcomes, 'express', float(final_amount), float(total_coef)
            )
            await conn.execute("UPDATE users SET balance = balance - $1 WHERE user_id = $2", float(final_amount), user_id)
            
        await message.answer(f"✅ Экспресс успешно оформлен!\n📊 Событий: {len(express_legs)}\n🎰 Сумма: {final_amount} | Итоговый кэф: {total_coef}")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка экспресса: {e}")
        await state.clear()

# =====================================================================
# 3. БОНУС И ИСТОРИЯ
# =====================================================================

@router.message(F.text == "🎁 Бонус")
async def get_bonus(message: Message):
    if not await is_subscribed(message.bot, message.from_user.id):
        return await message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    user_id = message.from_user.id
    try:
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                db_now = await conn.fetchval("SELECT NOW()")
                if db_now.tzinfo is not None:
                    db_now = db_now.replace(tzinfo=None) 
                    
                user_data = await conn.fetchrow("SELECT last_bonus FROM users WHERE user_id = $1 FOR UPDATE", user_id)
                
                if user_data and user_data['last_bonus']:
                    last_bonus = user_data['last_bonus']
                    if last_bonus.tzinfo is not None:
                        last_bonus = last_bonus.replace(tzinfo=None) 
                        
                    time_passed = db_now - last_bonus
                    cooldown = timedelta(hours=24)
                    
                    if time_passed < cooldown:
                        remaining_seconds = int((cooldown - time_passed).total_seconds())
                        if remaining_seconds > 0:
                            hours, remainder = divmod(remaining_seconds, 3600)
                            minutes, _ = divmod(remainder, 60)
                            return await message.answer(f"⏳ Возвращайтесь через **{hours} ч. {minutes} мин.**")
                
                reward = random.randint(50, 1000)
                await conn.execute("UPDATE users SET balance = balance + $1, last_bonus = NOW() WHERE user_id = $2", float(reward), user_id)
                new_balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
            
        await message.answer(f"🎁 Ежедневный бонус получен!\n\n+{reward}.0 ⭐️\n💰 Твой баланс: {new_balance:,.1f}")
    except Exception as e:
        await message.answer(f"❌ Ошибка при получении бонуса: {e}")

@router.message(F.text == "📊 Мои Ставки")
async def my_bets(message: Message):
    if not await is_subscribed(message.bot, message.from_user.id):
        return await message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    user_id = message.from_user.id
    try:
        async with db.pool.acquire() as conn:
            history = await conn.fetch(
                "SELECT match_ids, outcomes, amount, coef, status FROM bets WHERE user_id = $1 ORDER BY id DESC LIMIT 5", 
                user_id
            )
            
        if not history:
            return await message.answer("📊 У вас пока нет ставок.")
            
        text = "📊 Ваши последние ставки:\n\n"
        for idx, bet in enumerate(history, 1):
            status_emoji = "⏳ В ожидании" if bet['status'] == 'pending' else ("✅ Выиграла" if bet['status'] == 'won' else "❌ Проиграла")
            
            # Сокращаем коэффициент до десятых
            formatted_coef = round(float(bet['coef']), 1)
            
            text += f"{idx}. {status_emoji} | Кэф: {formatted_coef} | Сумма: {bet['amount']}\n"
            if len(bet['match_ids']) == 1:
                text += f"   Исход: {str(bet['outcomes'][0]).upper()}\n\n"
            else:
                text += f"   Исход: ЭКСПРЕСС ({', '.join([str(o).upper() for o in bet['outcomes']])})\n\n"
            
        await message.answer(text)
    except Exception as e:
        await message.answer(f"❌ Ошибка загрузки истории: {e}")

# =====================================================================
# 4. ПРОФИЛЬ И ДОП. МЕНЮ
# =====================================================================

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    if not await is_subscribed(message.bot, message.from_user.id):
        return await message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    user_id = message.from_user.id
    user_name = message.from_user.username or message.from_user.first_name
    try:
        async with db.pool.acquire() as conn:
            user_data = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
            if not user_data: 
                return await message.answer("❌ Профиль не найден.")
                
            balance = float(user_data['balance'])
            rank = await conn.fetchval("SELECT COUNT(*) + 1 FROM users WHERE balance > $1", balance)
            
            total_bets = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1", user_id) or 0
            won_bets = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1 AND status = 'won'", user_id) or 0
            winrate = int((won_bets / total_bets) * 100) if total_bets > 0 else 0
        
        await message.answer(
            f"👤 Профиль FTCL BET\n\n👤 Игрок: {user_name}\n💰 Баланс: {balance:,.1f} ⭐\n"
            f"🎰 Ставок: {total_bets}\n📈 Побед: {winrate}%\n📊 Место: #{rank}"
        )
    except Exception as e: 
        await message.answer(f"❌ Ошибка отображения профиля: {e}")

@router.message(F.text == "🏆 Топ 10")
async def show_top_10(message: Message):
    if not await is_subscribed(message.bot, message.from_user.id):
        return await message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    try:
        async with db.pool.acquire() as conn:
            top_users = await conn.fetch("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
        
        text = "🏆 ТОП 10 ИГРОКОВ FTCL BET 🏆\n\n"
        for index, user in enumerate(top_users, 1):
            try:
                chat = await message.bot.get_chat(user['user_id'])
                name = chat.username or chat.first_name
            except Exception:
                name = f"Игрок {user['user_id']}"
                
            text += f"{index}. {name} — {user['balance']:,.1f}\n"
        await message.answer(text)
    except Exception as e: 
        await message.answer(f"❌ Ошибка топа: {e}")

@router.message(F.text == "👥 Рефералка")
async def show_referral(message: Message):
    if not await is_subscribed(message.bot, message.from_user.id):
        return await message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    bot_info = await message.bot.get_me()
    await message.answer(
        "👥 Реферальная программа\n\nПолучай по 250 на баланс за друга!\n\n"
        f"Твоя ссылка:\nhttps://t.me/{bot_info.username}?start={message.from_user.id}"
    )

@router.message(F.text == "🎟 Промокоды")
async def promo_start(message: Message, state: FSMContext):
    if not await is_subscribed(message.bot, message.from_user.id):
        return await message.answer("❌ Вы не подписаны на все каналы!", reply_markup=sub_keyboard())

    await message.answer("🎟 Отправьте промокод в чат:")
    await state.set_state(PromoStates.waiting_for_code)

@router.message(PromoStates.waiting_for_code)
async def process_promo(message: Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id
    await state.clear()
    
    try:
        async with db.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS promocodes (code TEXT PRIMARY KEY, reward NUMERIC, uses_left INT);
                CREATE TABLE IF NOT EXISTS user_promos (user_id BIGINT, code TEXT);
            ''')
            
            promo = await conn.fetchrow("SELECT reward, uses_left FROM promocodes WHERE code = $1", code)
            if not promo:
                return await message.answer("❌ Промокод не найден.")
            if promo['uses_left'] <= 0:
                return await message.answer("❌ Лимит исчерпан.")
                
            used = await conn.fetchval("SELECT 1 FROM user_promos WHERE user_id = $1 AND code = $2", user_id, code)
            if used:
                return await message.answer("❌ Вы уже активировали этот код.")
                
            async with conn.transaction():
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", float(promo['reward']), user_id)
                await conn.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code = $1", code)
                await conn.execute("INSERT INTO user_promos (user_id, code) VALUES ($1, $2)", user_id, code)
            
            await message.answer(f"✅ Промокод активирован! Зачислено: {float(promo['reward'])}")
    except Exception as e:
        await message.answer(f"❌ Ошибка промокода: {e}")
