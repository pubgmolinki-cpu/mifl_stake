from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db
import json
import random
from datetime import datetime, timedelta

router = Router()

class BetStates(StatesGroup):
    waiting_for_amount = State()

class ExpressStates(StatesGroup):
    selecting_matches = State()   
    selecting_outcomes = State()  
    waiting_for_amount = State()  

class PromoStates(StatesGroup):
    waiting_for_code = State()

# Вспомогательная функция проверки заморозки ставок
async def check_bets_lock(conn) -> bool:
    await conn.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)")
    status = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'bets_locked'")
    return status == 'true'

# =====================================================================
# 1. МАТЧИ И СТАВКИ
# =====================================================================

@router.message(F.text == "📋 Матчи")
async def show_matches(message: Message):
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
    m_id = int(callback.data.split("_")[2])
    
    async with db.pool.acquire() as conn:
        if await check_bets_lock(conn):
            return await callback.answer("❌ Ставки временно заморожены администрацией (идет слив результатов/подсчет)!", show_alert=True)
            
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
    await callback.message.answer(f"📊 Выберите исход для одиночной ставки на матч {m_dict['title']}:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("bet_"))
async def select_bet_outcome(callback: CallbackQuery, state: FSMContext):
    async with db.pool.acquire() as conn:
        if await check_bets_lock(conn):
            return await callback.answer("❌ Ошибка: прием ставок только что был закрыт администратором!", show_alert=True)

    parts = callback.data.split("_")
    chosen_outcome = parts[1]
    match_id = int(parts[2])
    
    await state.update_data(bet_type=chosen_outcome, match_id=match_id)
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
    bet_type = state_data.get('bet_type') 
    match_id = state_data.get('match_id')
    
    if not bet_type or not match_id:
        await message.answer("❌ Ошибка: сессия потеряна. Начните заново через раздел Матчи.")
        await state.clear()
        return

    try:
        async with db.pool.acquire() as conn:
            if await check_bets_lock(conn):
                await state.clear()
                return await message.answer("❌ Администратор закрыл ставки. Ваша ставка отклонена!")

            balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
            if balance < bet_amount:
                return await message.answer("❌ Недостаточно средств на игровом балансе!")

            match_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", int(match_id))
            if not match_data:
                return await message.answer("❌ Матч больше не существует.")

            match_dict = dict(match_data)
            col_name = f"coef_{bet_type}"
            if bet_type == "tb2.5": col_name = "coef_tb"
            elif bet_type == "tm2.5": col_name = "coef_tm"
            elif bet_type == "oz": 
                col_name = "coef_oz_yes" if "coef_oz_yes" in match_dict else "coef_oz"
            
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

            # Исправлено: добавлено поле 'single' для колонки bet_type
            await conn.execute(
                "INSERT INTO bets (user_id, match_ids, outcomes, bet_type, amount, coef, status) VALUES ($1, ARRAY[$2::BIGINT], ARRAY[$3::TEXT], 'single', $4, $5, 'pending')",
                user_id, int(match_id), str(bet_type), float(bet_amount), float(coef)
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
    async with db.pool.acquire() as conn:
        if await check_bets_lock(conn):
            return await message.answer("❌ Экспрессы временно недоступны. Ставки заморожены админом.")

    await state.update_data(express_match_ids=[], express_legs=[])
    builder = InlineKeyboardBuilder()
    async with db.pool.acquire() as conn:
        active_matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    
    if not active_matches:
        return await message.answer("ℹ️ Сейчас нет активных матчей для экспресса.")

    for match in active_matches:
        builder.button(text=f"{match['title']}", callback_data=f"exp_toggle_{match['id']}")
    builder.button(text="✅ Подтвердить выбор", callback_data="exp_confirm_matches")
    builder.adjust(1)
    
    await message.answer("⚽ Выберите матчи для Экспресса, затем нажмите Подтвердить:", reply_markup=builder.as_markup())
    await state.set_state(ExpressStates.selecting_matches)

@router.callback_query(ExpressStates.selecting_matches, F.data.startswith("exp_toggle_"))
async def toggle_express_match(callback: CallbackQuery, state: FSMContext):
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
    data = await state.get_data()
    selected_ids = data.get("express_match_ids", [])
    if len(selected_ids) < 2:
        return await callback.answer("❌ Нужно выбрать минимум 2 матча!", show_alert=True)
        
    await state.update_data(current_index=0)
    first_match_id = selected_ids[0]
    
    builder = InlineKeyboardBuilder()
    for outcome in ["p1", "x", "p2", "tb2.5", "tm2.5", "oz"]:
        builder.button(text=outcome.upper(), callback_data=f"exp_choice_{outcome}_{first_match_id}")
    builder.adjust(3, 3)
    await callback.message.edit_text(f"📋 Шаг 1/{len(selected_ids)}: Выберите исход для матча ID {first_match_id}:", reply_markup=builder.as_markup())
    await state.set_state(ExpressStates.selecting_outcomes)

@router.callback_query(ExpressStates.selecting_outcomes, F.data.startswith("exp_choice_"))
async def process_express_outcome_step(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    outcome = parts[2]
    match_id = int(parts[3])
    
    data = await state.get_data()
    selected_ids = data.get("express_match_ids", [])
    express_legs = data.get("express_legs", [])
    current_index = data.get("current_index", 0)
    
    express_legs.append({"match_id": match_id, "bet_type": outcome})
    current_index += 1
    await state.update_data(express_legs=express_legs, current_index=current_index)
    
    if current_index < len(selected_ids):
        next_match_id = selected_ids[current_index]
        builder = InlineKeyboardBuilder()
        for outcome_type in ["p1", "x", "p2", "tb2.5", "tm2.5", "oz"]:
            builder.button(text=outcome_type.upper(), callback_data=f"exp_choice_{outcome_type}_{next_match_id}")
        builder.adjust(3, 3)
        await callback.message.edit_text(f"📋 Шаг {current_index + 1}/{len(selected_ids)}: Выберите исход для матча ID {next_match_id}:", reply_markup=builder.as_markup())
    else:
        await callback.message.edit_text("💰 Все исходы выбраны! Введите итоговую сумму ставки на экспресс:")
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
                return await message.answer("❌ Ставки закрыты администратором. Экспресс отклонён.")

            for leg in express_legs:
                m_id = leg['match_id']
                b_t = leg['bet_type']
                m_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", m_id)
                if m_data:
                    m_dict = dict(m_data)
                    col = f"coef_{b_t}"
                    if b_t == "tb2.5": col = "coef_tb"
                    elif b_t == "tm2.5": col = "coef_tm"
                    elif b_t == "oz": 
                        col = "coef_oz_yes" if "coef_oz_yes" in m_dict else "coef_oz"
                    total_coef *= float(m_dict.get(col) or 1.0)
            
            total_coef = round(total_coef, 1)
            balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
            if balance < final_amount:
                return await message.answer("❌ Недостаточно баланса для экспресса!")

            m_ids = [int(leg['match_id']) for leg in express_legs]
            outcomes = [str(leg['bet_type']) for leg in express_legs]
            
            # Исправлено: добавлено поле 'express' для колонки bet_type
            await conn.execute(
                "INSERT INTO bets (user_id, match_ids, outcomes, bet_type, amount, coef, status) VALUES ($1, $2, $3, 'express', $4, $5, 'pending')",
                user_id, m_ids, outcomes, float(final_amount), float(total_coef)
            )
            await conn.execute("UPDATE users SET balance = balance - $1 WHERE user_id = $2", float(final_amount), user_id)
            
        await message.answer(f"✅ Экспресс успешно оформлен!\n📊 Событий: {len(express_legs)}\n🎰 Сумма: {final_amount} | Итоговый кэф: {total_coef}")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка при регистрации экспресс-ставки: {e}")
        await state.clear()

# =====================================================================
# 3. БОНУС И ИСТОРИЯ
# =====================================================================

@router.message(F.text == "🎁 Бонус")
async def get_bonus(message: Message):
    user_id = message.from_user.id
    try:
        async with db.pool.acquire() as conn:
            # Исправление: берем время напрямую из БД, чтобы не было конфликтов часовых поясов
            db_now = await conn.fetchval("SELECT NOW()")
            user_data = await conn.fetchrow("SELECT last_bonus FROM users WHERE user_id = $1", user_id)
            
            if user_data and user_data['last_bonus']:
                time_passed = db_now - user_data['last_bonus']
                cooldown = timedelta(hours=24)
                
                if time_passed < cooldown:
                    # Исправление: total_seconds() гарантирует правильный расчет даже с разными днями/часами
                    remaining_seconds = int((cooldown - time_passed).total_seconds())
                    if remaining_seconds > 0:
                        hours, remainder = divmod(remaining_seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        return await message.answer(
                            f"⏳ Вы уже получали бонус!\n"
                            f"Возвращайтесь через **{hours} ч. {minutes} мин.**"
                        )
            
            # Рандомная награда от 50 до 1000 звёзд
            reward = random.randint(50, 1000)
            
            # Обновляем баланс и записываем время по времени сервера БД
            await conn.execute("UPDATE users SET balance = balance + $1, last_bonus = NOW() WHERE user_id = $2", float(reward), user_id)
            new_balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
            
        await message.answer(f"🎁 Ежедневный бонус получен!\n\nВам начислено +{reward}.0 ⭐️\n💰 Твой новый баланс: {new_balance:,.1f}")
    except Exception as e:
        await message.answer(f"❌ Ошибка при получении бонуса: {e}")

@router.message(F.text == "📊 Мои Ставки")
async def my_bets(message: Message):
    user_id = message.from_user.id
    try:
        async with db.pool.acquire() as conn:
            history = await conn.fetch(
                "SELECT match_ids, outcomes, amount, coef, status FROM bets WHERE user_id = $1 ORDER BY id DESC LIMIT 5", 
                user_id
            )
            
        if not history:
            return await message.answer("📊 У вас пока нет совершенных ставок.")
            
        text = "📊 Ваши последние ставки:\n\n"
        for idx, bet in enumerate(history, 1):
            status_emoji = "⏳ В ожидании" if bet['status'] == 'pending' else ("✅ Выиграла" if bet['status'] == 'won' else "❌ Проиграла")
            text += f"{idx}. {status_emoji} | Кэф: {bet['coef']} | Сумма: {bet['amount']}\n"
            
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
    user_id = message.from_user.id
    try:
        async with db.pool.acquire() as conn:
            user_data = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
            if not user_data: 
                return await message.answer("❌ Профиль не найден. Пожалуйста, напишите /start для регистрации.")
                
            balance = float(user_data['balance'])
            rank = await conn.fetchval("SELECT COUNT(*) + 1 FROM users WHERE balance > $1", balance)
            
            total_bets = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1", user_id) or 0
            won_bets = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1 AND status = 'won'", user_id) or 0
            winrate = int((won_bets / total_bets) * 100) if total_bets > 0 else 0
        
        profile_text = (
            f"👤 Профиль FTCL BET\n\n"
            f"🆔 ID: {user_id}\n"
            f"💰 Баланс: {balance:,.1f} ⭐\n"
            f"🎰 Ставок всего: {total_bets}\n"
            f"📈 Процент побед: {winrate}%\n"
            f"📊 Место в рейтинге: #{rank}"
        )
        await message.answer(profile_text)
        
    except Exception as e: 
        await message.answer(f"❌ Ошибка отображения профиля: {e}")

@router.message(F.text == "🏆 Топ 10")
async def show_top_10(message: Message):
    try:
        async with db.pool.acquire() as conn:
            top_users = await conn.fetch("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
        text = "🏆 ТОП 10 ИГРОКОВ FTCL BET 🏆\n\n"
        for index, user in enumerate(top_users, 1):
            text += f"{index}. ID: {user['user_id']} — {user['balance']:,.1f}\n"
        await message.answer(text)
    except Exception as e: await message.answer(f"❌ Ошибка топа: {e}")

@router.message(F.text == "👥 Рефералка")
async def show_referral(message: Message):
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username
    user_id = message.from_user.id
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    await message.answer(
        "👥 Реферальная программа\n\n"
        "Приглашай друзей и получай по 250 на баланс за каждого!\n\n"
        f"Твоя ссылка для приглашений:\n{ref_link}"
    )

@router.message(F.text == "🎟 Промокоды")
async def promo_start(message: Message, state: FSMContext):
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
                return await message.answer("❌ Лимит активаций этого промокода исчерпан.")
                
            used = await conn.fetchval("SELECT 1 FROM user_promos WHERE user_id = $1 AND code = $2", user_id, code)
            if used:
                return await message.answer("❌ Вы уже активировали этот промокод.")
                
            reward = float(promo['reward'])
            
            async with conn.transaction():
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", reward, user_id)
                await conn.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code = $1", code)
                await conn.execute("INSERT INTO user_promos (user_id, code) VALUES ($1, $2)", user_id, code)
            
            await message.answer(f"✅ Промокод успешно активирован! На баланс зачислено: {reward}")
    except Exception as e:
        await message.answer(f"❌ Ошибка промокода: {e}")
