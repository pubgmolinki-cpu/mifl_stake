from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db  # Подключаем твой модуль базы данных

router = Router()

# Состояния FSM для одиночных ставок и экспрессов
class BetStates(StatesGroup):
    waiting_for_amount = State()

class ExpressStates(StatesGroup):
    selecting_matches = State()   
    selecting_outcomes = State()  
    waiting_for_amount = State()  

# =====================================================================
# 1. СТРУКТУРА ОДИНОЧНОЙ СТАВКИ (ФИКС NULL И ИСПРАВЛЕНИЕ БАЗЫ)
# =====================================================================

@router.callback_query(F.data.startswith("bet_"))
async def select_bet_outcome(callback: CallbackQuery, state: FSMContext):
    chosen_outcome = callback.data.split("_")[1]
    await state.update_data(bet_type=chosen_outcome)
    await callback.message.answer(
        f"📊 Вы выбрали исход {chosen_outcome.upper()}.\n"
        "💰 Введите сумму ставки в чат:"
    )
    await state.set_state(BetStates.waiting_for_amount)
    await callback.answer()

@router.message(BetStates.waiting_for_amount)
async def accept_bet_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите сумму ставки цифрами (целое число).")
        return

    bet_amount = int(message.text)
    user_id = message.from_user.id
    
    state_data = await state.get_data()
    bet_type = state_data.get('bet_type') 
    match_id = state_data.get('match_id', 1)  # Дефолтное значение, если ID потерялся
    
    if not bet_type:
        await message.answer("❌ Ошибка: не удалось определить исход. Начните заново через 'Матчи'.")
        await state.clear()
        return

    try:
        # Исправлено: Обернуто в пул подключений к БД
        async with db.pool.acquire() as conn:
            # Проверяем баланс
            balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
            if balance < bet_amount:
                return await message.answer("❌ Недостаточно средств на игровом балансе!")

            # Вытягиваем коэффициент из матча
            match_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", int(match_id))
            col_name = f"coef_{bet_type}"
            if bet_type == "tb2.5": col_name = "coef_tb"
            elif bet_type == "tm2.5": col_name = "coef_tm"
            elif bet_type == "oz": col_name = "coef_oz_yes"
            
            coef = match_data.get(col_name, 2.0) if match_data else 2.0

            # Записываем в базу как массивы ARRAY (чтобы admin.py успешно считывал купоны)
            await conn.execute(
                "INSERT INTO bets (user_id, match_ids, outcomes, amount, coef, status) VALUES ($1, ARRAY[$2::int], ARRAY[$3::text], $4, $5, 'pending')",
                user_id, int(match_id), str(bet_type), bet_amount, float(coef)
            )
            # Списываем баланс
            await conn.execute("UPDATE users SET balance = balance - $1 WHERE user_id = $2", bet_amount, user_id)
            
        await message.answer(f"✅ Ставка успешно принята!\n🎰 Сумма: {bet_amount} ⭐ | Кэф: {coef}")
        await state.clear()

    except Exception as e:
        print(f"Ошибка при сохранении одиночной ставки: {e}")
        await message.answer("❌ Произошла ошибка при оформлении ставки.")
        await state.clear()

# =====================================================================
# 2. ПРОФИЛЬ С АВТО-ВИНРЕЙТОМ (ФИКС ОШИБКИ ПОДКЛЮЧЕНИЯ)
# =====================================================================

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    try:
        async with db.pool.acquire() as conn:
            user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
            if not user:
                return await message.answer("❌ Вы не зарегистрированы. Напишите /start")
                
            rank = await conn.fetchval("SELECT COUNT(*) + 1 FROM users WHERE balance > (SELECT balance FROM users WHERE user_id = $1)", user_id)
            total_bets = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1", user_id)
            won_bets = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1 AND status = 'won'", user_id)
            
            winrate = int((won_bets / total_bets) * 100) if total_bets > 0 else 0
            balance = user['balance']
        
        profile_text = (
            f"👤 Ваш профиль FTCL BET (3-4 Div)\n\n"
            f"🆔 Ваш ID: `{user_id}`\n"
            f"💰 Игровой баланс: {balance:,.1f} ⭐\n"
            f"🎰 Всего ставок: {total_bets}\n"
            f"📈 Винрейт: {winrate}%\n"
            f"📊 Место в топе: #{rank}"
        )
        await message.answer(profile_text)
    except Exception as e:
        print(f"Ошибка профиля: {e}")
        await message.answer("❌ Не удалось загрузить данные профиля.")

# =====================================================================
# 3. ТОП 10 (ФИКС ОШИБКИ ПОДКЛЮЧЕНИЯ)
# =====================================================================

@router.message(F.text == "🏆 Топ 10")
async def show_top_10(message: Message):
    try:
        async with db.pool.acquire() as conn:
            # Если у тебя в базе нет first_name или username, запрос упадет. 
            # На всякий случай запрашиваем user_id как резерв
            top_users = await conn.fetch("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
        
        text = "🏆 **ТОП 10 ИГРОКОВ FTCL BET** 🏆\n\n"
        for index, user in enumerate(top_users, 1):
            balance = user['balance']
            text += f"{index}. ID: `{user['user_id']}` — {balance:,.1f} ⭐\n"
            
        await message.answer(text)
    except Exception as e:
        print(f"Ошибка Топ 10: {e}")
        await message.answer("❌ Не удалось загрузить список топ-игроков.")

# =====================================================================
# 4. ПОШАГОВЫЙ ЭКСПРЕСС (ФИКС ОШИБКИ ПОДКЛЮЧЕНИЯ)
# =====================================================================

@router.message(F.text == "🚀 Экспресс")
async def start_express(message: Message, state: FSMContext):
    await state.update_data(express_match_ids=[], express_legs=[])
    
    builder = InlineKeyboardBuilder()
    async with db.pool.acquire() as conn:
        active_matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    
    if not active_matches:
        return await message.answer("ℹ️ Сейчас нет активных матчей для сбора экспресса.")

    for match in active_matches:
        builder.button(text=f"{match['title']}", callback_data=f"exp_toggle_{match['id']}")
    builder.button(text="✅ Подтвердить выбор матчей", callback_data="exp_confirm_matches")
    builder.adjust(1)
    
    await message.answer("⚽ Выберите матчи для добавления в Экспресс (нажимайте на кнопки, затем подтвердите):", reply_markup=builder.as_markup())
    await state.set_state(ExpressStates.selecting_matches)

@router.callback_query(ExpressStates.selecting_matches, F.data.startswith("exp_toggle_"))
async def toggle_express_match(callback: CallbackQuery, state: FSMContext):
    match_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected_ids = data.get("express_match_ids", [])
    
    if match_id in selected_ids:
        selected_ids.remove(match_id)
        await callback.answer("❌ Матч удален из списка")
    else:
        selected_ids.append(match_id)
        await callback.answer("✅ Матч добавлен в список")
        
    await state.update_data(express_match_ids=selected_ids)

@router.callback_query(ExpressStates.selecting_matches, F.data == "exp_confirm_matches")
async def confirm_matches_for_express(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_ids = data.get("express_match_ids", [])
    
    if len(selected_ids) < 2:
        await callback.answer("❌ Нужно выбрать как минимум 2 матча!", show_alert=True)
        return
        
    await state.update_data(current_index=0)
    first_match_id = selected_ids[0]
    
    builder = InlineKeyboardBuilder()
    for outcome in ["p1", "x", "p2", "tb2.5", "tm2.5", "oz"]:
        builder.button(text=outcome.upper(), callback_data=f"exp_choice_{outcome}_{first_match_id}")
    builder.adjust(3, 3)
    
    await callback.message.edit_text(
        f"📋 Шаг 1/{len(selected_ids)}: Выберите исход для матча ID {first_match_id}:",
        reply_markup=builder.as_markup()
    )
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
        
        await callback.message.edit_text(
            f"📋 Шаг {current_index + 1}/{len(selected_ids)}: Выберите исход для матча ID {next_match_id}:",
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text("💰 Все исходы выбраны! Введите итоговую сумму ставки на этот экспресс:")
        await state.set_state(ExpressStates.waiting_for_amount)
    await callback.answer()

@router.message(ExpressStates.waiting_for_amount)
async def accept_express_final_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Введите сумму цифрами.")
        
    final_amount = int(message.text)
    user_id = message.from_user.id
    data = await state.get_data()
    express_legs = data.get("express_legs", [])
    
    try:
        match_ids = [leg['match_id'] for leg in express_legs]
        outcomes = [leg['bet_type'] for leg in express_legs]
        
        total_coef = 1.0
        async with db.pool.acquire() as conn:
            # Считаем итоговый кэф перемножением
            for leg in express_legs:
                m_id = leg['match_id']
                b_t = leg['bet_type']
                m_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", m_id)
                if m_data:
                    col = f"coef_{b_t}"
                    if b_t == "tb2.5": col = "coef_tb"
                    elif b_t == "tm2.5": col = "coef_tm"
                    elif b_t == "oz": col = "coef_oz_yes"
                    total_coef *= m_data.get(col, 1.0)
            
            total_coef = round(total_coef, 2)
            
            # Проверка баланса
            balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
            if balance < final_amount:
                return await message.answer("❌ Недостаточно баланса для экспресса!")

            # Запись экспресса в базу данных
            await conn.execute(
                "INSERT INTO bets (user_id, match_ids, outcomes, amount, coef, status) VALUES ($1, $2, $3, $4, $5, 'pending')",
                user_id, match_ids, outcomes, final_amount, total_coef
            )
            await conn.execute("UPDATE users SET balance = balance - $1 WHERE user_id = $2", final_amount, user_id)
            
        await message.answer(f"✅ Экспресс из {len(express_legs)} матчей на сумму {final_amount} ⭐ успешно оформлен!\n📈 Общий кэф: {total_coef}")
        await state.clear()
    except Exception as e:
        print(f"Ошибка сохранения экспресса: {e}")
        await message.answer("❌ Ошибка при регистрации экспресс-ставки.")
        await state.clear()

# =====================================================================
# ЗАГОТОВКИ ДЛЯ ОСТАЛЬНЫХ КНОПОК (ЧТОБЫ НЕ БЫЛО ИГНОРА)
# Сюда ты можешь вставить свою старую логику выполнения!
# =====================================================================

@router.message(F.text == "📋 Матчи")
async def show_matches(message: Message, state: FSMContext):
    # Тут должен быть вывод списка активных матчей для одиночных ставок
    builder = InlineKeyboardBuilder()
    async with db.pool.acquire() as conn:
        active_matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    
    if not active_matches:
        return await message.answer("🎰 На данный момент нет активных матчей.")
        
    text = "⚽ Выберите матч для одиночной ставки:\n\n"
    for m in active_matches:
        text += f"🔹 ID {m['id']} — {m['title']}\n"
        # Для примера вешаем кнопку выбора исхода на первый матч
        builder.button(text=f"Матч {m['id']}", callback_data=f"select_match_{m['id']}")
    
    builder.adjust(2)
    await message.answer(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("select_match_"))
async def step_match_outcomes(callback: CallbackQuery, state: FSMContext):
    m_id = int(callback.data.split("_")[2])
    await state.update_data(match_id=m_id)
    
    builder = InlineKeyboardBuilder()
    for outcome in ["p1", "x", "p2", "tb2.5", "tm2.5", "oz"]:
        builder.button(text=outcome.upper(), callback_data=f"bet_{outcome}")
    builder.adjust(3, 3)
    await callback.message.answer(f"Выберите исход для одиночной ставки на матч ID {m_id}:", reply_markup=builder.as_markup())
    await callback.answer()

@router.message(F.text == "👥 Рефералка")
async def show_referral(message: Message):
    # Твоя логика генерации реф-ссылки бота: t.me/bot?start=ref_ID
    bot_username = "ТВОЙ_ЮЗЕРНЕЙМ_БОТА"  # Поменяй на юзер своего бота без @
    ref_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
    await message.answer(f"👥 **Реферальная программа**\n\nПриглашай друзей и получай по 250 ⭐ за каждого!\n\nТвоя ссылка:\n`{ref_link}`")

@router.message(F.text == "🎁 Бонус")
async def get_bonus(message: Message):
    # Напиши сюда выдачу ежедневного бонуса
    await message.answer("🎁 Бонус пока в разработке, возвращайтесь позже!")

@router.message(F.text == "📊 Мои Ставки")
async def my_bets(message: Message):
    # Вывод истории купонов
    await message.answer("📊 Раздел истории ставок заполняется...")

@router.message(F.text == "🎟 Промокоды")
async def use_promo(message: Message):
    # Активация промокодов игроками
    await message.answer("🎟 Введите промокод, чтобы получить звёзды:")
