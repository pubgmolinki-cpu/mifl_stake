import json
import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command
from database import db

router = Router()
logger = logging.getLogger(__name__)

# Сюда впиши свой Telegram ID
ADMIN_IDS = [1866813859] 

class AutoMatchStates(StatesGroup):
    team1_data = State()
    team2_data = State()

class SettleMatchStates(StatesGroup):
    match_id = State()
    score = State()

class InteractiveBetStates(StatesGroup):
    title = State()
    options = State()

def clip_coef(val: float) -> float:
    return max(1.15, min(7.50, val))

def parse_team_form(scores_str: str) -> dict:
    scores = scores_str.strip().split()
    goals_scored, goals_conceded, points, btts_count, total_matches = 0, 0, 0, 0, 0

    for s in scores:
        if ":" in s:
            try:
                g1, g2 = map(int, s.split(":"))
                goals_scored += g1
                goals_conceded += g2
                total_matches += 1
                if g1 > g2: points += 3
                elif g1 == g2: points += 1
                if g1 > 0 and g2 > 0: btts_count += 1
            except ValueError: continue
                
    return {"points": points, "scored": goals_scored, "conceded": goals_conceded, "btts": btts_count, "matches": total_matches if total_matches > 0 else 3}

# ==========================================
# 1. АДМИН-ПАНЕЛЬ
# ==========================================
@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return

    kb = [
        [types.KeyboardButton(text="➕ Авто-матч"), types.KeyboardButton(text="🎭 Создать Интерактив")],
        [types.KeyboardButton(text="🏁 Завершить матч"), types.KeyboardButton(text="📋 Список активных матчей")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    
    await message.answer(
        "🛠 **Панель администратора**\n\n"
        "• `/add_auto` — Сгенерировать матч по форме\n"
        "• `/add_inter` — Добавить долгосрочный интерактив\n"
        "• `/settle` — Расчет ставок по счету\n"
        "• `/give_balance ID СУММА` — Начислить баланс игроку",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ==========================================
# 2. АВТОГЕНЕРАЦИЯ МАТЧА С ОКРУГЛЕНИЕМ ДО .1
# ==========================================
@router.message(Command("add_auto"))
@router.message(F.text == "➕ Авто-матч")
async def start_auto_match(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("⚽️ **Автогенерация матча**\n\nВведите **НАЗВАНИЕ 1-й команды** и **3 счета**.\n📝 *Пример:* `Рапид, 2:1 1:1 3:0`")
    await state.set_state(AutoMatchStates.team1_data)

@router.message(AutoMatchStates.team1_data)
async def process_team1(message: types.Message, state: FSMContext):
    if "," not in message.text:
        return await message.answer("❌ Разделяйте имя и результаты запятой!")
    name, scores = message.text.split(",", 1)
    await state.update_data(t1_name=name.strip(), t1_stats=parse_team_form(scores))
    await message.answer("✅ Принято. Теперь отправьте данные **Второй команды** в таком же формате:")
    await state.set_state(AutoMatchStates.team2_data)

@router.message(AutoMatchStates.team2_data)
async def process_team2(message: types.Message, state: FSMContext):
    if "," not in message.text:
        return await message.answer("❌ Не забывайте про запятую!")

    name2, scores2 = message.text.split(",", 1)
    stats2 = parse_team_form(scores2)
    
    user_data = await state.get_data()
    name1, stats1 = user_data['t1_name'], user_data['t1_stats']

    strength1 = max(1.0, stats1['points'] + (stats1['scored'] - stats1['conceded']) * 0.5 + 5)
    strength2 = max(1.0, stats2['points'] + (stats2['scored'] - stats2['conceded']) * 0.5 + 5)
    total_strength = strength1 + strength2
    
    margin, prob_x = 0.92, 0.28
    prob_p1 = (strength1 / total_strength) * 0.72
    prob_p2 = (strength2 / total_strength) * 0.72
    
    # 🔥 ОКРУГЛЕНИЕ КОЭФФИЦИЕНТОВ ДО 1 ЗНАКА ПОСЛЕ ЗАПЯТОЙ (.1)
    coef_p1 = round(clip_coef(1 / (prob_p1 * margin)), 1)
    coef_p2 = round(clip_coef(1 / (prob_p2 * margin)), 1)
    coef_x = round(clip_coef(1 / (prob_x * margin)), 1)

    avg_goals = ((stats1['scored'] + stats1['conceded']) / stats1['matches'] + (stats2['scored'] + stats2['conceded']) / stats2['matches']) / 2
    if avg_goals >= 2.5:
        coef_tb = round(clip_coef(1.5 + (4.0 - avg_goals) * 0.2), 1)
        coef_tm = round(clip_coef(2.3 + (avg_goals - 2.5) * 0.3), 1)
    else:
        coef_tb = round(clip_coef(2.2 + (2.5 - avg_goals) * 0.3), 1)
        coef_tm = round(clip_coef(1.6 + (avg_goals - 1.0) * 0.2), 1)

    btts_prob = max(0.2, min(0.8, (stats1['btts'] / stats1['matches'] + stats2['btts'] / stats2['matches']) / 2))
    coef_oz_yes = round(clip_coef(1 / (btts_prob * margin)), 1)
    coef_oz_no = round(clip_coef(1 / ((1 - btts_prob) * margin)), 1)

    match_title = f"{name1} — {name2.strip()}"
    
    async with db.pool.acquire() as conn:
        await conn.execute(
            '''INSERT INTO matches (title, coef_p1, coef_x, coef_p2, coef_tb, coef_tm, coef_oz_yes, coef_oz_no, status) 
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'active')''',
            match_title, coef_p1, coef_x, coef_p2, coef_tb, coef_tm, coef_oz_yes, coef_oz_no
        )

    await message.answer(
        f"🎉 **Матч опубликован!**\n\n🏆 **{match_title}**\n"
        f"• П1: `{coef_p1}` | Х: `{coef_x}` | П2: `{coef_p2}`\n"
        f"• ТБ(2.5): `{coef_tb}` | ТМ(2.5): `{coef_tm}`\n"
        f"• ОЗ(Да): `{coef_oz_yes}` | ОЗ(Нет): `{coef_oz_no}`"
    )
    await state.clear()

# ==========================================
# 3. ДОБАВЛЕНИЕ ИНТЕРАКТИВОВ
# ==========================================
@router.message(Command("add_inter"))
@router.message(F.text == "🎭 Создать Интерактив")
async def start_interactive(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("🏆 **Новый Интерактив**\n\nВведите заголовок события:\n📝 *Пример: Победитель 5 сезона лиги ФТКЛ!*")
    await state.set_state(InteractiveBetStates.title)

@router.message(InteractiveBetStates.title)
async def process_inter_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("✅ Заголовок сохранен.\nТеперь отправьте список исходов и кэфов (**каждый с новой строки через запятую**):\n\n📝 *Пример:*\n`Рапид, 4.3`\n`Спартак, 2.5`")
    await state.set_state(InteractiveBetStates.options)

@router.message(InteractiveBetStates.options)
async def process_inter_options(message: types.Message, state: FSMContext):
    lines = message.text.split("\n")
    options_dict = {}
    for line in lines:
        if "," not in line:
            return await message.answer(f"❌ Ошибка в строке `{line}`. Забыли запятую!")
        name, coef = line.split(",", 1)
        try: options_dict[name.strip()] = round(float(coef.strip()), 1)
        except ValueError: return await message.answer("❌ Коэффициент должен быть числом!")

    data = await state.get_data()
    async with db.pool.acquire() as conn:
        await conn.execute("INSERT INTO interactive_bets (title, options) VALUES ($1, $2)", data['title'], json.dumps(options_dict, ensure_ascii=False))
        
    await message.answer(f"🎉 Событие **«{data['title']}»** успешно добавлено в линию!")
    await state.clear()

# ==========================================
# 4. РАСЧЕТ СТАВОК ПО СЧЕТУ
# ==========================================
@router.message(Command("settle"))
@router.message(F.text == "🏁 Завершить матч")
async def start_settle_match(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    async with db.pool.acquire() as conn:
        active_matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    if not active_matches:
        return await message.answer("ℹ️ Нет активных матчей для расчета.")

    text = "🔎 **Выберите ID матча для закрытия:**\n\n"
    for m in active_matches: text += f"• ID: `{m['id']}` — **{m['title']}**\n"
    await message.answer(text, parse_mode="Markdown")
    await state.set_state(SettleMatchStates.match_id)

@router.message(SettleMatchStates.match_id)
async def process_settle_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ ID должен быть числом!")
    await state.update_data(match_id=int(message.text))
    await message.answer("⚽️ Введите финальный счет матча (например `2:0`):")
    await state.set_state(SettleMatchStates.score)

@router.message(SettleMatchStates.score)
async def process_settle_score(message: types.Message, state: FSMContext):
    if ":" not in message.text: return await message.answer("❌ Формат счета через двоеточие!")
    data = await state.get_data()
    m_id, score_str = data['match_id'], message.text.strip()
    g1, g2 = map(int, score_str.split(":"))

    winning = []
    winning.append("p1" if g1 > g2 else "x" if g1 == g2 else "p2")
    winning.append("tb" if (g1 + g2) > 2.5 else "tm")
    winning.append("oz_yes" if g1 > 0 and g2 > 0 else "oz_no")

    async with db.pool.acquire() as conn:
        match_info = await conn.fetchrow("SELECT title FROM matches WHERE id = $1", m_id)
        if not match_info: return await message.answer("❌ Матч не найден.")

        await conn.execute("UPDATE matches SET status = 'finished' WHERE id = $1", m_id)
        bets = await conn.fetch("SELECT * FROM bets WHERE status = 'pending' AND $1 = ANY(match_ids)", m_id)

        count = 0
        for b in bets:
            if b['outcomes'][0] in winning:
                win_sum = b['amount'] * b['coef']
                await conn.execute("UPDATE bets SET status = 'won' WHERE id = $1", b['id'])
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", win_sum, b['user_id'])
                try: await message.bot.send_message(b['user_id'], f"🟢 **Ставка №{b['id']} выиграла!**\nМатч: {match_info['title']} ({score_str})\n💰 +`{round(win_sum, 1)}` ⭐️")
                except Exception: pass
            else:
                await conn.execute("UPDATE bets SET status = 'lost' WHERE id = $1", b['id'])
                try: await message.bot.send_message(b['user_id'], f"🔴 **Ставка №{b['id']} проиграла.**\nМатч: {match_info['title']} ({score_str})")
                except Exception: pass
            count += 1

    await message.answer(f"🏁 Матч **{match_info['title']}** закрыт ({score_str}). Рассчитано ставок: `{count}`.")
    await state.clear()

# ==========================================
# 5. СПИСОК И ВЫДАЧА БАЛАНСА
# ==========================================
@router.message(F.text == "📋 Список активных матчей")
async def list_active_matches(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    async with db.pool.acquire() as conn:
        matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    if not matches: return await message.answer("Матчей нет.")
    text = "🎰 **Активные матчи:**\n\n"
    for m in matches: text += f"• ID: `{m['id']}` — {m['title']}\n"
    await message.answer(text)

@router.message(Command("give_balance"))
async def give_balance_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    args = message.text.split()
    if len(args) < 3: return await message.answer("❌ Формат: `/give_balance [ID] [Сумма]`")
    
    target, amount = int(args[1]), float(args[2])
    async with db.pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, target)
    await message.answer(f"💰 Выдано +{amount} игроку `{target}`.")
