from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from database import db
from keyboards import match_outcome_keyboard
from states import BetStates

router = Router()

@router.message(F.text == "📋 Матчи")
async def list_matches(message: types.Message):
    matches = await db.get_active_matches()
    if not matches:
        await message.answer("📬 Активных матчей нет. Следите за обновлениями!")
        return
        
    for m in matches:
        text = (
            f"⚽️ **{m['title']}**\n\n"
            f"П1: {m['coef_p1']} | Х: {m['coef_x']} | П2: {m['coef_p2']}\n"
            f"ТБ(2.5): {m['coef_tb']} | ТМ(2.5): {m['coef_tm']}\n"
            f"ОЗ(Да): {m['coef_oz_yes']} | ОЗ(Нет): {m['coef_oz_no']}"
        )
        await message.answer(text, reply_markup=match_outcome_keyboard(m['id']), parse_mode="Markdown")

# Обработка выбора исхода для одиночной ставки
@router.callback_query(F.data.startswith("bet_"))
async def process_single_bet_selection(callback: types.CallbackQuery, state: FSMContext):
    _, match_id, outcome = callback.data.split("_")
    
    async with db.pool.acquire() as conn:
        match = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", int(match_id))
        
    coef_map = {'p1': 'coef_p1', 'x': 'coef_x', 'p2': 'coef_p2', 'tb': 'coef_tb', 'tm': 'coef_tm', 'ozy': 'coef_oz_yes', 'ozn': 'coef_oz_no'}
    coef = match[coef_map[outcome]]
    
    await state.update_data(match_id=int(match_id), outcome=outcome, coef=coef, title=match['title'])
    await callback.message.answer(f"Вы выбрали исход **{outcome.upper()}** на матч **{match['title']}** (Кэф: {coef}).\nВведите сумму ставки:")
    await state.set_state(BetStates.single_bet_amount)
    await callback.answer()

@router.message(BetStates.single_bet_amount)
async def finish_single_bet(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите корректную сумму числом.")
        return
        
    amount = int(message.text)
    user = await db.get_user(message.from_user.id)
    
    if amount > user['balance'] or amount <= 0:
        await message.answer("Недостаточно средств или неверная сумма.")
        return
        
    data = await state.get_data()
    await db.update_balance(message.from_user.id, -amount)
    await db.add_bet(message.from_user.id, [data['match_id']], [data['outcome']], 'single', amount, data['coef'])
    
    await message.answer(f"✅ Ставка принята!\nМатч: {data['title']}\nИсход: {data['outcome'].upper()}\nСумма: {amount} ⭐️")
    await state.clear()

# Логика экспресса
@router.message(F.text == "🎰 Экспресс")
async def start_express(message: types.Message, state: FSMContext):
    matches = await db.get_active_matches()
    if len(matches) < 2:
        await message.answer("📬 Недостаточно матчей для экспресса (нужно минимум 2).")
        return
        
    await state.update_data(express_matches=[], express_outcomes=[], current_coef=1.0)
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[])
    for m in matches:
        kb.inline_keyboard.append([InlineKeyboardButton(text=m['title'], callback_data=f"expadd_{m['id']}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="📥 Завершить выбор матчей", callback_data="exp_done")])
    
    await message.answer("Выберите матчи для сборки экспресса:", reply_markup=kb)
    await state.set_state(BetStates.express_select_matches)

@router.callback_query(F.data.startswith("expadd_"), BetStates.express_select_matches)
async def add_match_to_express(callback: types.CallbackQuery, state: FSMContext):
    match_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    
    if match_id in data['express_matches']:
        await callback.answer("Этот матч уже добавлен!", show_alert=True)
        return
        
    data['express_matches'].append(match_id)
    await state.update_data(express_matches=data['express_matches'])
    await callback.answer("Матч добавлен!")

@router.callback_query(F.data == "exp_done", BetStates.express_select_matches)
async def process_express_outcomes(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data['express_matches']) < 2:
        await callback.answer("Выберите как минимум 2 матча!", show_alert=True)
        return
        
    # Переходим к выбору исходов поочередно
    await next_express_outcome(callback.message, state)
    await callback.answer()

async def next_express_outcome(message: types.Message, state: FSMContext):
    data = await state.get_data()
    chosen_count = len(data['express_outcomes'])
    total_count = len(data['express_matches'])
    
    if chosen_count < total_count:
        match_id = data['express_matches'][chosen_count]
        async with db.pool.acquire() as conn:
            match = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", match_id)
        
        # Передаем клавиатуру для выбора исхода, но с флагом exp_
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="П1", callback_data=f"expout_{match_id}_p1"),
             InlineKeyboardButton(text="Х", callback_data=f"expout_{match_id}_x"),
             InlineKeyboardButton(text="П2", callback_data=f"expout_{match_id}_p2")],
            [InlineKeyboardButton(text="ТБ 2.5", callback_data=f"expout_{match_id}_tb"),
             InlineKeyboardButton(text="ТМ 2.5", callback_data=f"expout_{match_id}_tm")]
        ])
        await message.answer(f"Выберите исход для матча **{match['title']}**:", reply_markup=kb, parse_mode="Markdown")
        await state.set_state(BetStates.express_select_outcomes)
    else:
        await message.answer(f"Все исходы выбраны! Итоговый коэффициент: {data['current_coef']:.2f}.\nВведите сумму ставки для экспресса:")
        await state.set_state(BetStates.express_bet_amount)

@router.callback_query(F.data.startswith("expout_"), BetStates.express_select_outcomes)
async def save_express_outcome(callback: types.CallbackQuery, state: FSMContext):
    _, match_id, outcome = callback.data.split("_")
    data = await state.get_data()
    
    async with db.pool.acquire() as conn:
        match = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", int(match_id))
        
    coef_map = {'p1': 'coef_p1', 'x': 'coef_x', 'p2': 'coef_p2', 'tb': 'coef_tb', 'tm': 'coef_tm'}
    coef = match[coef_map[outcome]]
    
    data['express_outcomes'].append(outcome)
    data['current_coef'] *= coef
    await state.update_data(express_outcomes=data['express_outcomes'], current_coef=data['current_coef'])
    
    await callback.message.delete()
    await next_express_outcome(callback.message, state)
    await callback.answer()

@router.message(BetStates.express_bet_amount)
async def finish_express_bet(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите сумму числом.")
        return
        
    amount = int(message.text)
    user = await db.get_user(message.from_user.id)
    
    if amount > user['balance'] or amount <= 0:
        await message.answer("Недостаточно средств.")
        return
        
    data = await state.get_data()
    await db.update_balance(message.from_user.id, -amount)
    await db.add_bet(message.from_user.id, data['express_matches'], data['express_outcomes'], 'express', amount, data['current_coef'])
    
    await message.answer(f"✅ Экспресс ставка принята!\nКоличество событий: {len(data['express_matches'])}\nОбщий кэф: {data['current_coef']:.2f}\nСумма: {amount} ⭐️")
    await state.clear()
