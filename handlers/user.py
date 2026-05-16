import json
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db

router = Router()
logger = logging.getLogger(__name__)

class UserBetStates(StatesGroup):
    waiting_for_amount = State()

class ExpressStates(StatesGroup):
    waiting_for_amount = State()

class PromoStates(StatesGroup):
    waiting_for_code = State()

# ==========================================
# ПРОФИЛЬ, ТОП 10, РЕФЕРАЛКА, БОНУС
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
        f"👤 Ваш профиль FTCL BET (3-4 Div)\n\n"
        f"🆔 Твой ID: {message.from_user.id}\n"
        f"💰 Игровой баланс: {round(balance, 1)} ⭐️\n"
        f"📊 Всего сделано ставок: {bets_count}"
    )

@router.message(F.text == "🏆 Топ 10")
async def show_top_players(message: types.Message):
    async with db.pool.acquire() as conn:
        leaders = await conn.fetch("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
        
    text = "🏆 Топ 10 богатых игроков лиги:\n\n"
    for i, player in enumerate(leaders, 1):
        text += f"{i}. ID {player['user_id']} — {round(player['balance'], 1)} ⭐️\n"
    await message.answer(text)

@router.message(F.text == "👥 Рефералка")
async def show_referral_system(message: types.Message):
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    
    async with db.pool.acquire() as conn:
        ref_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referred_by = $1", message.from_user.id)
        
    await message.answer(
        f"👥 Реферальная система\n\n"
        f"Приглашайте друзей и получайте бонус за каждого нового участника!\n"
        f"🎁 Награда: +250.0 ⭐️ на ваш баланс.\n\n"
        f"Количество ваших рефералов: {ref_count}\n"
        f"🔗 Ваша реферальная ссылка:\n{ref_link}"
    )

@router.message(F.text == "🎁 Бонус")
async def get_bonus(message: types.Message):
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT last_bonus FROM users WHERE user_id = $1", message.from_user.id)
        now = datetime.now()
        if user and user['last_bonus'] and (now - user['last_bonus']) < timedelta(hours=24):
            time_passed = now - user['last_bonus']
            seconds_left = 86400 - time_passed.total_seconds()
            return await message.answer(f"⏳ Бонус уже получен! Приходите через: {int(seconds_left // 3600)}ч. {int((seconds_left % 3600) // 60)}мин.")

        bonus_amount = 500.0
        await conn.execute("UPDATE users SET balance = balance + $1, last_bonus = $2 WHERE user_id = $3", bonus_amount, now, message.from_user.id)
    await message.answer(f"🎉 Вам начислено: +{round(bonus_amount, 1)} ⭐️")

@router.message(F.text == "📊 Мои Ставки")
async def my_bets(message: types.Message):
    async with db.pool.acquire() as conn:
        bets = await conn.fetch("SELECT id, amount, coef, status FROM bets WHERE user_id = $1 ORDER BY id DESC LIMIT 5", message.from_user.id)
    if not bets:
        return await message.answer("ℹ️ У вас пока нет ставок.")

    text = "📝 Последние 5 купонов:\n\n"
    for b in bets:
        status_emoji = "🟢 Выигрыш" if b['status'] == 'won' else "🔴 Проигрыш" if b['status'] == 'lost' else "⏳ В игре"
        text += f"{status_emoji} | Купон #{b['id']}\nСумма: {round(b['amount'], 1)} ⭐️ | Кэф: {round(b['coef'], 1)}\n"
        text += "—" * 15 + "\n"
    await message.answer(text)

# ==========================================
# ОДИНОЧНЫЕ СТАВКИ
# ==========================================
@router.message(F.text == "📋 Матчи")
async def show_matches_inline(message: types.Message):
    async with db.pool.acquire() as conn:
        matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active' ORDER BY id DESC")
    if not matches:
        return await message.answer("😔 На данный момент нет активных матчей.")

    builder = [[InlineKeyboardButton(text=f"⚽️ {m['title']}", callback_data=f"match_{m['id']}")] for m in matches]
    await message.answer("👇 Выберите матч для одиночной ставки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=builder))

@router.callback_query(F.data.startswith("match_"))
async def handle_match_choice(callback: types.CallbackQuery):
    match_id = int(callback.data.split("_")[1])
    async with db.pool.acquire() as conn:
        m = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", match_id)
    if not m or m['status'] != 'active':
        return await callback.answer("❌ Матч уже завершен.")

    text = f"🏆 {m['title']}\n\nВыберите исход:"
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
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("bet_"))
async def process_bet_selection(callback: types.CallbackQuery, state: FSMContext):
    _, match_id, outcome, coef = callback.data.split("_", 3)
    await state.update_data(match_id=int(match_id), outcome=outcome, coef=float(coef))
    await callback.message.answer(f"📊 Вы выбрали исход {outcome.upper()} с коэффициентом {coef}.\n💰 Введите сумму ставки в чат:")
    await state.set_state(UserBetStates.waiting_for_amount)
    await callback.answer()

@router.message(UserBetStates.waiting_for_amount)
async def accept_bet_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Сумма ставки должна быть целым числом!")
    amount = float(message.text)
    if amount <= 0:
        return await message.answer("❌ Сумма должна быть больше нуля!")

    data = await state.get_data()
    await state.clear()

    try:
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", message.from_user.id)
                if not user or user['balance'] < amount:
                    return await message.answer("❌ Недостаточно средств на балансе!")

                await conn.execute("UPDATE users SET balance = balance - $1 WHERE user_id = $2", amount, message.from_user.id)
                await conn.execute(
                    "INSERT INTO bets (user_id, match_ids, outcomes, coef, amount, status) VALUES ($1, $2, $3, $4, $5, 'pending')",
                    message.from_user.id, [data['match_id']], [data['outcome']], data['coef'], amount
                )
        await message.answer(f"✅ Ставка принята!\nИсход: {data['outcome'].upper()} | Кэф: {data['coef']}\nСумма: {amount} ⭐️")
    except Exception as e:
        logger.error(f"Ошибка при сохранении одиночной ставки: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка на сервере при оформлении ставки. Попробуйте еще раз.")

# ==========================================
# МОДУЛЬ ЭКСПРЕСС-СТАВОК
# ==========================================
@router.message(F.text == "🚀 Экспресс")
async def start_express_setup(message: types.Message, state: FSMContext):
    await state.clear()
    async with db.pool.acquire() as conn:
        matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active' ORDER BY id DESC")
    if not matches:
        return await message.answer("😔 На данный момент нет активных матчей для экспресса.")

    await state.update_data(express_list=[])
    builder = [[InlineKeyboardButton(text=f"⚽️ {m['title']}", callback_data=f"expmatch_{m['id']}")] for m in matches]
    await message.answer("🚀 Конструктор Экспресса\nВыберите первый матч для добавления в купон:", reply_markup=InlineKeyboardMarkup(inline_keyboard=builder))

@router.callback_query(F.data.startswith("expmatch_"))
async def express_match_markets(callback: types.CallbackQuery):
    match_id = int(callback.data.split("_")[1])
    async with db.pool.acquire() as conn:
        m = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", match_id)
    
    text = f"🚀 Добавление в Экспресс:\n🏆 {m['title']}"
    kb = [
        [
            InlineKeyboardButton(text=f"П1 ({round(m['coef_p1'], 1)})", callback_data=f"expadd_{match_id}_p1_{round(m['coef_p1'], 1)}_{m['title']}"),
            InlineKeyboardButton(text=f"Х ({round(m['coef_x'], 1)})", callback_data=f"expadd_{match_id}_x_{round(m['coef_x'], 1)}_{m['title']}"),
            InlineKeyboardButton(text=f"П2 ({round(m['coef_p2'], 1)})", callback_data=f"expadd_{match_id}_p2_{round(m['coef_p2'], 1)}_{m['title']}")
        ]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("expadd_"))
async def add_outcome_to_express(callback: types.CallbackQuery, state: FSMContext):
    _, match_id, outcome, coef, m_title = callback.data.split("_", 4)
    data = await state.get_data()
    express_list = data.get("express_list", [])

    if any(item['match_id'] == int(match_id) for item in express_list):
        return await callback.answer("❌ Вы уже добавили исход из этого матча!", show_alert=True)

    express_list.append({"match_id": int(match_id), "title": m_title, "outcome": outcome, "coef": float(coef)})
    await state.update_data(express_list=express_list)

    total_coef = 1.0
    text = "🚀 Ваш Купон Экспресса:\n\n"
    for idx, item in enumerate(express_list, 1):
        total_coef *= item['coef']
        text += f"{idx}. {item['title']} | Исход: {item['outcome'].upper()} (кэф {item['coef']})\n"
    
    total_coef = round(total_coef, 2)
    text += f"\nИтоговый коэффициент: {total_coef}"

    kb = [
        [InlineKeyboardButton(text="➕ Добавить ещё матч", callback_data="exp_continue")],
        [InlineKeyboardButton(text="💰 Поставить экспресс", callback_data="exp_place")],
        [InlineKeyboardButton(text="🗑 Очистить", callback_data="exp_clear")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "exp_continue")
async def express_continue(callback: types.CallbackQuery, state: FSMContext):
    async with db.pool.acquire() as conn:
        matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active' ORDER BY id DESC")
    builder = [[InlineKeyboardButton(text=f"⚽️ {m['title']}", callback_data=f"expmatch_{m['id']}")] for m in matches]
    await callback.message.edit_text("Выберите следующий матч:", reply_markup=InlineKeyboardMarkup(inline_keyboard=builder))

@router.callback_query(F.data == "exp_clear")
async def express_clear(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🗑 Купон экспресса полностью очищен.")

@router.callback_query(F.data == "exp_place")
async def express_place_order(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    express_list = data.get("express_list", [])
    if len(express_list) < 2:
        return await callback.answer("❌ Для экспресса нужно минимум 2 матча!", show_alert=True)
    
    await callback.message.answer("💰 Введите сумму ставки на этот экспресс:")
    await state.set_state(ExpressStates.waiting_for_amount)
    await callback.answer()

@router.message(ExpressStates.waiting_for_amount)
async def accept_express_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Сумма должна быть целым числом!")
    amount = float(message.text)
    if amount <= 0:
        return await message.answer("❌ Сумма должна быть больше нуля!")

    data = await state.get_data()
    express_list = data.get("express_list", [])
    await state.clear()

    match_ids = [item['match_id'] for item in express_list]
    outcomes = [item['outcome'] for item in express_list]
    
    total_coef = 1.0
    for item in express_list:
        total_coef *= item['coef']
    total_coef = round(total_coef, 1)

    try:
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", message.from_user.id)
                if not user or user['balance'] < amount:
                    return await message.answer("❌ Недостаточно средств на балансе!")

                await conn.execute("UPDATE users SET balance = balance - $1 WHERE user_id = $2", amount, message.from_user.id)
                await conn.execute(
                    "INSERT INTO bets (user_id, match_ids, outcomes, coef, amount, status) VALUES ($1, $2, $3, $4, $5, 'pending')",
                    message.from_user.id, match_ids, outcomes, total_coef, amount
                )
        await message.answer(f"✅ Экспресс успешно принят!\nМатчей в купоне: {len(match_ids)}\nОбщий кэф: {total_coef}\nСумма: {amount} ⭐️")
    except Exception as e:
        logger.error(f"Ошибка при сохранении экспресс-ставки: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка на сервере при оформлении экспресса. Попробуйте еще раз.")

# ==========================================
# МОДУЛЬ ПРОМОКОДОВ
# ==========================================
@router.message(F.text == "🎟 Промокоды")
async def promo_enter_cmd(message: types.Message, state: FSMContext):
    await message.answer("🎟 Введите действующий промокод:")
    await state.set_state(PromoStates.waiting_for_code)

@router.message(PromoStates.waiting_for_code)
async def activate_promocode(message: types.Message, state: FSMContext):
    code_entered = message.text.strip()
    await state.clear()

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            promo = await conn.fetchrow("SELECT * FROM promocodes WHERE code = $1", code_entered)
            if not promo:
                return await message.answer("❌ Такого промокода не существует или он устарел.")

            if promo['uses_left'] <= 0:
                return await message.answer("😔 Этот промокод больше не доступен для активации (закончились использования).")

            already_used = await conn.fetchval("SELECT COUNT(*) FROM user_promos WHERE user_id = $1 AND code = $2", message.from_user.id, code_entered)
            if already_used > 0:
                return await message.answer("❌ Вы уже активировали этот промокод ранее!")

            await conn.execute("INSERT INTO user_promos (user_id, code) VALUES ($1, $2)", message.from_user.id, code_entered)
            await conn.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code = $1", code_entered)
            await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", promo['reward'], message.from_user.id)
            
    await message.answer(f"🎉 Промокод успешно активирован! На ваш счет зачислено +{round(promo['reward'], 1)} ⭐️")
