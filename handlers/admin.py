import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command
from database import db

router = Router()
logger = logging.getLogger(__name__)

# СПИСОК ID АДМИНИСТРАТОРОВ (Замени на свой Telegram ID)
ADMIN_IDS = [1866813859] 

# Состояния FSM для создания матча
class AutoMatchStates(StatesGroup):
    team1_data = State()
    team2_data = State()

# Состояния FSM для закрытия матча
class SettleMatchStates(StatesGroup):
    match_id = State()
    score = State()


def clip_coef(val: float) -> float:
    return max(1.15, min(7.50, val))


def parse_team_form(scores_str: str) -> dict:
    scores = scores_str.strip().split()
    goals_scored = 0
    goals_conceded = 0
    points = 0
    btts_count = 0  
    total_matches = 0

    for s in scores:
        if ":" in s:
            try:
                g1, g2 = map(int, s.split(":"))
                goals_scored += g1
                goals_conceded += g2
                total_matches += 1
                
                if g1 > g2:
                    points += 3
                elif g1 == g2:
                    points += 1
                
                if g1 > 0 and g2 > 0:
                    btts_count += 1
            except ValueError:
                continue
                
    return {
        "points": points,
        "scored": goals_scored,
        "conceded": goals_conceded,
        "btts": btts_count,
        "matches": total_matches if total_matches > 0 else 3
    }


# ==========================================
# 1. ГЛАВНАЯ АДМИН-ПАНЕЛЬ
# ==========================================

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    # Кнопки управления для админа
    kb = [
        [types.KeyboardButton(text="➕ Авто-матч"), types.KeyboardButton(text="🏁 Завершить матч")],
        [types.KeyboardButton(text="📋 Список активных матчей")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    
    await message.answer(
        "🛠 **Панель администратора FTCL/MIFL STAKE**\n\n"
        "Выберите нужное действие на клавиатуре или используйте команды:\n"
        "• `/add_auto` — Создать матч по форме команд\n"
        "• `/settle` — Закрыть матч и рассчитать ставки\n"
        "• `/give_balance ID СУММА` — Начислить баланс игроку",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


# ==========================================
# 2. КОМАНДА: АВТОМАТИЧЕСКОЕ СОЗДАНИЕ МАТЧА
# ==========================================

@router.message(Command("add_auto"))
@router.message(F.text == "➕ Авто-матч")
async def start_auto_match(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    
    await message.answer(
        "⚽️ **Автогенерация матча по форме команд**\n\n"
        "Введите **НАЗВАНИЕ первой команды** и **3 последних счета** через запятую.\n"
        "📝 **Пример:** `МФЛ Старс, 2:1 1:1 3:0`"
    )
    await state.set_state(AutoMatchStates.team1_data)


@router.message(AutoMatchStates.team1_data)
async def process_team1(message: types.Message, state: FSMContext):
    if "," not in message.text:
        await message.answer("❌ Обязательно ставьте запятую после названия команды!")
        return

    name, scores = message.text.split(",", 1)
    stats = parse_team_form(scores)
    await state.update_data(t1_name=name.strip(), t1_stats=stats)
    
    await message.answer(
        f"✅ Команда **{name.strip()}** сохранена.\n"
        f"Теперь введите данные второй команды:\n"
        f"📝 **Пример:** `ФТКЛ Юнайтед, 1:2 0:0 4:1`"
    )
    await state.set_state(AutoMatchStates.team2_data)


@router.message(AutoMatchStates.team2_data)
async def process_team2(message: types.Message, state: FSMContext):
    if "," not in message.text:
        await message.answer("❌ Обязательно ставьте запятую после названия команды!")
        return

    name2, scores2 = message.text.split(",", 1)
    stats2 = parse_team_form(scores2)
    name2 = name2.strip()

    user_data = await state.get_data()
    name1 = user_data['t1_name']
    stats1 = user_data['t1_stats']

    # Расчет сил и маржи
    strength1 = max(1.0, stats1['points'] + (stats1['scored'] - stats1['conceded']) * 0.5 + 5)
    strength2 = max(1.0, stats2['points'] + (stats2['scored'] - stats2['conceded']) * 0.5 + 5)
    total_strength = strength1 + strength2
    
    margin = 0.92
    prob_p1 = (strength1 / total_strength) * 0.72
    prob_p2 = (strength2 / total_strength) * 0.72
    prob_x = 0.28  
    
    coef_p1 = round(clip_coef(1 / (prob_p1 * margin)), 2)
    coef_p2 = round(clip_coef(1 / (prob_p2 * margin)), 2)
    coef_x = round(clip_coef(1 / (prob_x * margin)), 2)

    avg_goals = ((stats1['scored'] + stats1['conceded']) / stats1['matches'] + 
                 (stats2['scored'] + stats2['conceded']) / stats2['matches']) / 2
                 
    if avg_goals >= 2.5:
        coef_tb = round(clip_coef(1.5 + (4.0 - avg_goals) * 0.2), 2)
        coef_tm = round(clip_coef(2.3 + (avg_goals - 2.5) * 0.3), 2)
    else:
        coef_tb = round(clip_coef(2.2 + (2.5 - avg_goals) * 0.3), 2)
        coef_tm = round(clip_coef(1.6 + (avg_goals - 1.0) * 0.2), 2)

    btts_prob = max(0.2, min(0.8, (stats1['btts'] / stats1['matches'] + stats2['btts'] / stats2['matches']) / 2))
    coef_oz_yes = round(clip_coef(1 / (btts_prob * margin)), 2)
    coef_oz_no = round(clip_coef(1 / ((1 - btts_prob) * margin)), 2)

    match_title = f"{name1} — {name2}"
    
    async with db.pool.acquire() as conn:
        await conn.execute(
            '''INSERT INTO matches (title, coef_p1, coef_x, coef_p2, coef_tb, coef_tm, coef_oz_yes, coef_oz_no, status) 
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'active')''',
            match_title, coef_p1, coef_x, coef_p2, coef_tb, coef_tm, coef_oz_yes, coef_oz_no
        )

    await message.answer(
        f"🎉 **Матч создан!**\n\n🏆 **{match_title}**\n"
        f"• П1: `{coef_p1}` | Х: `{coef_x}` | П2: `{coef_p2}`\n"
        f"• ТБ(2.5): `{coef_tb}` | ТМ(2.5): `{coef_tm}`\n"
        f"• ОЗ(Да): `{coef_oz_yes}` | ОЗ(Нет): `{coef_oz_no}`"
    )
    await state.clear()


# ==========================================
# 3. СИСТЕМА: ЗАКРЫТИЕ МАТЧЕЙ И РАСЧЕТ СТАВОК
# ==========================================

@router.message(Command("settle"))
@router.message(F.text == "🏁 Завершить матч")
async def start_settle_match(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return

    async with db.pool.acquire() as conn:
        active_matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    
    if not active_matches:
        await message.answer("ℹ️ Нет активных матчей для завершения.")
        return

    text = "🔎 **Выберите ID матча для расчета ставок:**\n\n"
    for m in active_matches:
        text += f"• ID: `{m['id']}` — **{m['title']}**\n"
    
    await message.answer(text, parse_mode="Markdown")
    await state.set_state(SettleMatchStates.match_id)


@router.message(SettleMatchStates.match_id)
async def process_settle_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ID должен быть числом!")
        return
        
    await state.update_data(match_id=int(message.text))
    await message.answer("⚽️ Теперь введите **финальный счет** матча.\n📝 Пример: `2:0` или `1:1`")
    await state.set_state(SettleMatchStates.score)


@router.message(SettleMatchStates.score)
async def process_settle_score(message: types.Message, state: FSMContext):
    if ":" not in message.text:
        await message.answer("❌ Формат счета должен быть через двоеточие! Пример: `3:1`")
        return

    data = await state.get_data()
    m_id = data['match_id']
    score_str = message.text.strip()
    
    try:
        g1, g2 = map(int, score_str.split(":"))
    except ValueError:
        await message.answer("❌ Ошибка в числах счета. Введите заново.")
        return

    # Список выигравших исходов для этого матча
    winning_outcomes = []
    if g1 > g2: winning_outcomes.append("p1")
    elif g1 == g2: winning_outcomes.append("x")
    else: winning_outcomes.append("p2")

    if (g1 + g2) > 2.5: winning_outcomes.append("tb")
    else: winning_outcomes.append("tm")

    if g1 > 0 and g2 > 0: winning_outcomes.append("oz_yes")
    else: winning_outcomes.append("oz_no")

    async with db.pool.acquire() as conn:
        # Получаем данные матча
        match_info = await conn.fetchrow("SELECT title FROM matches WHERE id = $1", m_id)
        if not match_info:
            await message.answer("❌ Матч с таким ID не найден.")
            await state.clear()
            return

        # Переводим статус матча в 'finished'
        await conn.execute("UPDATE matches SET status = 'finished' WHERE id = $1", m_id)

        # Выбираем все нерассчитанные ставки, где есть этот матч
        bets = await conn.fetch("SELECT * FROM bets WHERE status = 'pending' AND $1 = ANY(match_ids)", m_id)

        calculated_count = 0
        for bet in bets:
            # Для простоты логики (одинары): берем исход ставки
            # Если у тебя экспрессы, тут будет сверка всех элементов массива
            user_outcome = bet['outcomes'][0] 
            
            if user_outcome in winning_outcomes:
                # Ставка выиграла
                win_sum = bet['amount'] * bet['coef']
                await conn.execute("UPDATE bets SET status = 'won' WHERE id = $1", bet['id'])
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", win_sum, bet['user_id'])
                
                # Уведомляем игрока (опционально, если bot доступен в контексте)
                try:
                    await message.bot.send_message(
                        bet['user_id'], 
                        f"🟢 **Ваша ставка №{bet['id']} выиграла!**\nМатч: {match_info['title']} ({score_str})\n"
                        f"💰 Начислено: `+{round(win_sum, 2)}` звезд!"
                    )
                except Exception: pass
            else:
                # Ставка проиграла
                await conn.execute("UPDATE bets SET status = 'lost' WHERE id = $1", bet['id'])
                try:
                    await message.bot.send_message(
                        bet['user_id'], 
                        f"🔴 **Ваша ставка №{bet['id']} проиграла.**\nМатч: {match_info['title']} ({score_str})"
                    )
                except Exception: pass
                
            calculated_count += 1

    await message.answer(
        f"🏁 **Матч {match_info['title']} успешно закрыт!**\n"
        f"📊 Финальный счет: `{score_str}`\n"
        f"♻️ Обработано и рассчитано ставок: `{calculated_count}`"
    )
    await state.clear()


# ==========================================
# 4. ВЫВОД СПИСКА АКТИВНЫХ МАТЧЕЙ (ДЛЯ ИНФО)
# ==========================================

@router.message(F.text == "📋 Список активных матчей")
async def list_active_matches(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return

    async with db.pool.acquire() as conn:
        matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    
    if not matches:
        await message.answer("Матчей пока нет.")
        return
        
    text = "🎰 **Текущие открытые матчи в базе:**\n\n"
    for m in matches:
        text += f"• ID: `{m['id']}` — {m['title']}\n"
    await message.answer(text, parse_mode="Markdown")


# ==========================================
# 5. КОМАНДА: НАЧИСЛЕНИЕ ВАЛЮТЫ ИГРОКУ
# ==========================================

@router.message(Command("give_balance"))
async def give_balance_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("❌ Формат команды: `/give_balance [ID_пользователя] [сумма]`")
        return

    target_id = int(args[1])
    try:
        amount = float(args[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом!")
        return

    async with db.pool.acquire() as conn:
        user_exists = await conn.fetchrow("SELECT user_id FROM users WHERE user_id = $1", target_id)
        if not user_exists:
            await message.answer("❌ Такого пользователя нет в базе данных бота.")
            return
            
        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, target_id)

    await message.answer(f"💰 Баланс пользователя `{target_id}` успешно изменен на `+{amount}`.")
    try:
        await message.bot.send_message(target_id, f"💳 Администратор начислил вам `+{amount}` игровых звезд на баланс!")
    except Exception: pass
