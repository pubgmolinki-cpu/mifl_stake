from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

# Все необходимые состояния FSM
class BetStates(StatesGroup):
    waiting_for_amount = State()

class ExpressStates(StatesGroup):
    selecting_matches = State()   # Выбор матчей кликами
    selecting_outcomes = State()  # Поочередный выбор исходов для каждого матча
    waiting_for_amount = State()  # Ввод итоговой суммы экспресса

# =====================================================================
# 1. ОДИНОЧНЫЕ СТАВКИ (ФИКС ОШИБКИ NULL)
# =====================================================================

@router.callback_query(F.data.startswith("bet_"))
async def select_bet_outcome(callback: CallbackQuery, state: FSMContext):
    # Вытаскиваем выбранный исход из callback_data
    chosen_outcome = callback.data.split("_")[1]
    
    # Записываем исход в стейт, чтобы колонка bet_type не была пустой
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
    
    # Читаем сохраненный bet_type из FSM-стейта
    state_data = await state.get_data()
    bet_type = state_data.get('bet_type') 
    match_id = state_data.get('match_id')
    
    if not bet_type:
        await message.answer("❌ Ошибка: не удалось определить исход. Начните заново через 'Матчи'.")
        await state.clear()
        return

    try:
        # Переменная bet_type теперь гарантированно строка, а не null
        await conn.execute(
            "INSERT INTO bets (user_id, match_id, bet_type, amount, status) VALUES ($1, $2, $3, $4, $5)",
            user_id, match_id, bet_type, bet_amount, 'pending'
        )
        await message.answer("✅ Ставка успешно принята!")
        await state.clear()

    except Exception as e:
        print(f"ERROR:handlers.user: Ошибка при сохранении одиночной ставки: {e}")
        await message.answer("❌ Произошла ошибка на сервере при оформлении ставки. Попробуйте еще раз.")

# =====================================================================
# 2. ОБНОВЛЕННЫЙ ТОП 10 (НИКНЕЙМ (@ЮЗЕР) – БАЛАНС)
# =====================================================================

@router.message(F.text == "🏆 Топ 10")
async def show_top_10(message: Message):
    try:
        top_users = await conn.fetch(
            "SELECT first_name, username, balance FROM users ORDER BY balance DESC LIMIT 10"
        )
        
        text = "🏆 ТОП 10 ИГРОКОВ FTCL BET 🏆\n\n"
        for index, user in enumerate(top_users, 1):
            nickname = user['first_name'] or "Игрок"
            username = f"(@{user['username']})" if user['username'] else "(нет юзера)"
            balance = user['balance']
            text += f"{index}. {nickname} {username} – {balance:,.1f} ⭐\n"
            
        await message.answer(text)
    except Exception as e:
        print(f"Ошибка при выводе Топ 10: {e}")
        await message.answer("❌ Не удалось загрузить список топ-игроков.")

# =====================================================================
# 3. ОБНОВЛЕННЫЙ ПРОФИЛЬ С АВТО-ВИНРЕЙТОМ
# =====================================================================

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    try:
        user = await conn.fetchrow(
            "SELECT first_name, username, balance FROM users WHERE user_id = $1", user_id
        )
        # Динамический расчет места в топе
        rank = await conn.fetchval(
            "SELECT COUNT(*) + 1 FROM users WHERE balance > (SELECT balance FROM users WHERE user_id = $1)", user_id
        )
        # Считаем ставки для винрейта
        total_bets = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1", user_id)
        won_bets = await conn.fetchval("SELECT COUNT(*) FROM bets WHERE user_id = $1 AND status = 'won'", user_id)
        
        winrate = int((won_bets / total_bets) * 100) if total_bets > 0 else 0
        
        nickname = user['first_name'] or "Не указан"
        username = f"@{user['username']}" if user['username'] else "@нет"
        balance = user['balance']
        
        profile_text = (
            f"👤Ваш профиль FTCL BET (3-4 Div)\n\n"
            f"👤 Ник ({username}) – ID {user_id}\n"
            f"💰 Игровой баланс – {balance:,.1f} ⭐\n"
            f"🎰 Всего ставок – {total_bets}\n"
            f"📈 Винрейт – {winrate}%\n"
            f"📊 Место в топе – #{rank}"
        )
        await message.answer(profile_text)
    except Exception as e:
        print(f"Ошибка при генерации профиля: {e}")
        await message.answer("❌ Ошибка при генерации профиля.")

# =====================================================================
# 4. ПОШАГОВЫЙ ЭКСПРЕСС (МАТЧИ -> ПОДТВЕРДИТЬ -> ИСХОДЫ -> СУММА)
# =====================================================================

@router.message(F.text == "🚀 Экспресс")
async def start_express(message: Message, state: FSMContext):
    await state.update_data(express_match_ids=[], express_legs=[])
    
    builder = InlineKeyboardBuilder()
    active_matches = await conn.fetch("SELECT id, team1, team2 FROM matches WHERE status = 'active'")
    
    for match in active_matches:
        builder.button(text=f"{match['team1']} — {match['team2']}", callback_data=f"exp_toggle_{match['id']}")
    builder.button(text="✅ Подтвердить выбор матчей", callback_data="exp_confirm_matches")
    builder.adjust(1)
    
    await message.answer("⚽ Выберите матчи для добавления в Экспресс (минимум 2):", reply_markup=builder.as_markup())
    await state.set_state(ExpressStates.selecting_matches)

@router.callback_query(ExpressStates.selecting_matches, F.data.startswith("exp_toggle_"))
async def toggle_express_match(callback: CallbackQuery, state: FSMContext):
    match_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected_ids = data.get("express_match_ids", [])
    
    if match_id in selected_ids:
        selected_ids.remove(match_id)
        await callback.answer("❌ Матч удален из экспресса")
    else:
        selected_ids.append(match_id)
        await callback.answer("✅ Матч добавлен")
        
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
        await message.answer("❌ Введите сумму цифрами.")
        return
        
    final_amount = int(message.text)
    data = await state.get_data()
    express_legs = data.get("express_legs", [])
    
    try:
        # Твоя SQL-логика сохранения экспресса в базу данных
        await message.answer(f"✅ Экспресс из {len(express_legs)} матчей на сумму {final_amount} ⭐ успешно оформлен!")
        await state.clear()
    except Exception as e:
        print(f"Ошибка сохранения экспресса: {e}")
        await message.answer("❌ Ошибка при регистрации экспресс-ставки.")
