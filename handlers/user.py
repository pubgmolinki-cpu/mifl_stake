from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db

router = Router()

class BetStates(StatesGroup):
    waiting_for_amount = State()

class ExpressStates(StatesGroup):
    selecting_matches = State()   
    selecting_outcomes = State()  
    waiting_for_amount = State()  

# =====================================================================
# 1. РАЗДЕЛ МАТЧИ (БЕЗ ЗВЁЗДОЧЕК, КЭФЫ ДО ДЕСЯТЫХ)
# =====================================================================

@router.message(F.text == "📋 Матчи")
async def show_matches(message: Message):
    builder = InlineKeyboardBuilder()
    async with db.pool.acquire() as conn:
        active_matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    
    if not active_matches:
        return await message.answer("🎰 На данный момент нет активных матчей.")
        
    text = "Выберите матч на который готовы поставить! 👇"
    
    for m in active_matches:
        builder.button(text=f"{m['title']}", callback_data=f"select_match_{m['id']}")
    
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("select_match_"))
async def step_match_outcomes(callback: CallbackQuery, state: FSMContext):
    m_id = int(callback.data.split("_")[2])
    await state.update_data(match_id=m_id)
    
    async with db.pool.acquire() as conn:
        match_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", m_id)
        
    if not match_data:
        return await callback.answer("❌ Матч не найден.", show_alert=True)
        
    m_dict = dict(match_data)
    
    # Округляем коэффициенты до десятых до вывода на кнопки
    c_p1 = round(float(m_dict.get("coef_p1", 2.0)), 1)
    c_x = round(float(m_dict.get("coef_x", 2.0)), 1)
    c_p2 = round(float(m_dict.get("coef_p2", 2.0)), 1)
    c_tb = round(float(m_dict.get("coef_tb", 2.0)), 1)
    c_tm = round(float(m_dict.get("coef_tm", 2.0)), 1)
    c_oz = round(float(m_dict.get("coef_oz", m_dict.get("coef_oz_yes", 2.0))), 1)

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
    parts = callback.data.split("_")
    chosen_outcome = parts[1]
    match_id = int(parts[2])
    
    await state.update_data(bet_type=chosen_outcome, match_id=match_id)
    await callback.message.answer(
        f"📊 Вы выбрали исход {chosen_outcome.upper()}.\n"
        "💰 Введите сумму ставки в чат:"
    )
    await state.set_state(BetStates.waiting_for_amount)
    await callback.answer()

# =====================================================================
# 2. ФИКС ОДИНОЧНОЙ СТАВКИ (ДОБАВЛЕН CAST К NUMERIC И ОКРУГЛЕНИЕ)
# =====================================================================

@router.message(BetStates.waiting_for_amount)
async def accept_bet_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите сумму ставки цифрами.")
        return

    bet_amount = int(message.text)
    user_id = message.from_user.id
    
    state_data = await state.get_data()
    bet_type = state_data.get('bet_type') 
    match_id = state_data.get('match_id')
    
    if not bet_type or not match_id:
        await message.answer("❌ Ошибка: сессия потеряна. Начните заново через 'Матчи'.")
        await state.clear()
        return

    try:
        async with db.pool.acquire() as conn:
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
            elif bet_type == "oz": col_name = "coef_oz" if "coef_oz" in match_dict else "coef_oz_yes"
            
            coef = round(float(match_dict.get(col_name, 2.0)), 1)

            # Примечание: Если в твоей старой базе поля назывались match_id и outcome (НЕ массивы),
            # измени ниже колонки match_ids -> match_id, outcomes -> outcome и убери списки [] у переменных.
            await conn.execute(
                "INSERT INTO bets (user_id, match_ids, outcomes, amount, coef, status) VALUES ($1, $2, $3, $4, $5::numeric, 'pending')",
                user_id, [int(match_id)], [str(bet_type)], bet_amount, coef
            )
            await conn.execute("UPDATE users SET balance = balance - $1::numeric WHERE user_id = $2", bet_amount, user_id)
            
        await message.answer(f"✅ Ставка успешно принята!\n🎰 Сумма: {bet_amount} ⭐ | Кэф: {coef}")
        await state.clear()

    except Exception as e:
        print(f"Ошибка одиночной ставки: {e}")
        await message.answer("❌ Произошла ошибка при оформлении ставки.")
        await state.clear()

# =====================================================================
# 3. ФИКС ЭКСПРЕССА (ОКРУГЛЕНИЕ КЭФА И ФИКС ТИПОВ ДАННЫХ)
# =====================================================================

@router.message(F.text == "🚀 Экспресс")
async def start_express(message: Message, state: FSMContext):
    await state.update_data(express_match_ids=[], express_legs=[])
    builder = InlineKeyboardBuilder()
    async with db.pool.acquire() as conn:
        active_matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    
    if not active_matches:
        return await message.answer("ℹ️ Сейчас нет active матчей для экспресса.")

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
        
    final_amount = int(message.text)
    user_id = message.from_user.id
    data = await state.get_data()
    express_legs = data.get("express_legs", [])
    
    try:
        match_ids = [leg['match_id'] for leg in express_legs]
        outcomes = [leg['bet_type'] for leg in express_legs]
        total_coef = 1.0
        
        async with db.pool.acquire() as conn:
            for leg in express_legs:
                m_id = leg['match_id']
                b_t = leg['bet_type']
                m_data = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", m_id)
                if m_data:
                    m_dict = dict(m_data)
                    col = f"coef_{b_t}"
                    if b_t == "tb2.5": col = "coef_tb"
                    elif b_t == "tm2.5": col = "coef_tm"
                    elif b_t == "oz": col = "coef_oz" if "coef_oz" in m_dict else "coef_oz_yes"
                    total_coef *= float(m_dict.get(col, 1.0))
            
            total_coef = round(total_coef, 1)
            balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
            if balance < final_amount:
                return await message.answer("❌ Недостаточно баланса для экспресса!")

            await conn.execute(
                "INSERT INTO bets (user_id, match_ids, outcomes, amount, coef, status) VALUES ($1, $2, $3, $4, $5::numeric, 'pending')",
                user_id, match_ids, outcomes, final_amount, total_coef
            )
            await conn.execute("UPDATE users SET balance = balance - $1::numeric WHERE user_id = $2", final_amount, user_id)
            
        await message.answer(f"✅ Экспресс успешно оформлен!\n📊 Количество событий: {len(express_legs)}\n🎰 Сумма: {final_amount} ⭐ | Итоговый кэф: {total_coef}")
        await state.clear()
    except Exception as e:
        print(f"Ошибка сохранения экспресса: {e}")
        await message.answer("❌ Ошибка при регистрации экспресс-ставки.")
        await state.clear()

# =====================================================================
# 4. ВОССТАНОВЛЕННЫЕ КНОПКИ БОНУС И МОИ СТАВКИ (БЕЗ ЗВЁЗДОЧЕК)
# =====================================================================

@router.message(F.text == "🎁 Бонус")
async def get_bonus(message: Message):
    user_id = message.from_user.id
    try:
        async with db.pool.acquire() as conn:
            await conn.execute("UPDATE users SET balance = balance + 150.0 WHERE user_id = $1", user_id)
            new_balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
            
        await message.answer(f"🎁 Ежедневный бонус получен!\n\nВам начислено +150.0 ⭐\n💰 Ваш новый баланс: {new_balance:,.1f} ⭐")
    except Exception as e:
        print(f"Ошибка Бонус: {e}")
        await message.answer("❌ Произошла ошибка при получении бонуса.")

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
            
        text = "📊 Ваши последние 5 ставок:\n\n"
        for idx, bet in enumerate(history, 1):
            status_emoji = "⏳" if bet['status'] == 'pending' else ("✅" if bet['status'] == 'won' else "❌")
            outcomes_str = ", ".join(bet['outcomes']).upper()
            bet_type_name = "Одинар" if len(bet['match_ids']) == 1 else "Экспресс"
            
            text += f"{idx}. {status_emoji} {bet_type_name} | Кэф: {bet['coef']} | Сумма: {bet['amount']} ⭐\n"
            text += f"   Исходы: {outcomes_str} | Статус: {bet['status']}\n\n"
            
        await message.answer(text)
    except Exception as e:
        print(f"Ошибка Мои Ставки: {e}")
        await message.answer("❌ Не удалось загрузить историю ваших ставок.")

# =====================================================================
# ПРОФИЛЬ, ТОП 10, РЕФЕРАЛКА И ПРОМОКОДЫ (БЕЗ ЗВЁЗДОЧЕК)
# =====================================================================

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    try:
        async with db.pool.acquire() as conn:
            user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
            if not user: return await message.answer("❌ Напишите /start")
            rank = await conn.fetchval("SELECT COUNT(*) + 1 FROM users WHERE balance > (SELECT balance FROM users WHERE user_id = $1)", user_id)
            total_bets = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1", user_id)
            won_bets = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1 AND status = 'won'", user_id)
            winrate = int((won_bets / total_bets) * 100) if total_bets > 0 else 0
        
        await message.answer(f"👤 Профиль FTCL BET\n\n🆔 ID: {user_id}\n💰 Баланс: {user['balance']:,.1f} ⭐\n🎰 Всего ставок: {total_bets}\n📈 Винрейт: {winrate}%\n📊 Место в топе: #{rank}")
    except Exception: await message.answer("❌ Ошибка профиля.")

@router.message(F.text == "🏆 Топ 10")
async def show_top_10(message: Message):
    try:
        async with db.pool.acquire() as conn:
            top_users = await conn.fetch("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
        text = "🏆 ТОП 10 ИГРОКОВ FTCL BET 🏆\n\n"
        for index, user in enumerate(top_users, 1):
            text += f"{index}. ID: {user['user_id']} — {user['balance']:,.1f} ⭐\n"
        await message.answer(text)
    except Exception: await message.answer("❌ Ошибка загрузки топа.")

@router.message(F.text == "👥 Рефералка")
async def show_referral(message: Message):
    await message.answer("👥 Реферальная программа\n\nПриглашай друзей и получай по 250 ⭐ за каждого!\n\nТвоя ссылка выводится в твоем боте.")

@router.message(F.text == "🎟 Промокоды")
async def use_promo(message: Message):
    await message.answer("🎟 Функция ввода промокодов проверяется администрацией.")
