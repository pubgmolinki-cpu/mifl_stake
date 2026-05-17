import json
import logging
import re
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command
from database import db

router = Router()
logger = logging.getLogger(__name__)

ADMIN_IDS = [1866813859]  # Твой Telegram ID

class AutoMatchStates(StatesGroup):
    team1_data = State()
    team2_data = State()

class SettleMatchStates(StatesGroup):
    match_id = State()
    score = State()

class PromoCreateStates(StatesGroup):
    waiting_for_data = State()

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
# АДМИН-ПАНЕЛЬ И БЛОКИРОВКИ
# ==========================================
@router.message(Command("admin"))
@router.message(F.text == "⚙️ Админ-панель")
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return

    kb = [
        [types.KeyboardButton(text="➕ Авто-матч"), types.KeyboardButton(text="🎟 Создать Промокод")],
        [types.KeyboardButton(text="🏁 Завершить матч"), types.KeyboardButton(text="📋 Список активных матчей")],
        [types.KeyboardButton(text="🔒 Закрыть ставки"), types.KeyboardButton(text="🔓 Открыть ставки")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("🛠 **Панель администратора FTCL**", reply_markup=keyboard)

@router.message(F.text == "🔒 Закрыть ставки")
async def lock_bets_manually(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    async with db.pool.acquire() as conn:
        await conn.execute("UPDATE bot_settings SET value = 'true' WHERE key = 'bets_locked'")
    await message.answer("🔒 Ставки ЗАМОРОЖЕНЫ.")

@router.message(F.text == "🔓 Открыть ставки")
async def unlock_bets_manually(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    async with db.pool.acquire() as conn:
        await conn.execute("UPDATE bot_settings SET value = 'false' WHERE key = 'bets_locked'")
    await message.answer("🔓 Ставки ОТКРЫТЫ.")

# ==========================================
# АВТОГЕНЕРАЦИЯ МАТЧА
# ==========================================
@router.message(Command("add_auto"))
@router.message(F.text == "➕ Авто-матч")
async def start_auto_match(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("⚽️ Введите НАЗВАНИЕ 1-й команды и 3 счета.\nПример: `Рапид, 2:1 1:1 3:0`")
    await state.set_state(AutoMatchStates.team1_data)

@router.message(AutoMatchStates.team1_data)
async def process_team1(message: types.Message, state: FSMContext):
    if "," not in message.text: return await message.answer("❌ Разделяйте имя и результаты запятой!")
    name, scores = message.text.split(",", 1)
    await state.update_data(t1_name=name.strip(), t1_stats=parse_team_form(scores))
    await message.answer("✅ Принято. Теперь Вторая команда:")
    await state.set_state(AutoMatchStates.team2_data)

@router.message(AutoMatchStates.team2_data)
async def process_team2(message: types.Message, state: FSMContext):
    if "," not in message.text: return await message.answer("❌ Не забывайте про запятую!")
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

    await message.answer(f"🎉 **Матч опубликован!**\n🏆 {match_title}")
    await state.clear()

# ==========================================
# ПРОМОКОДЫ АДМИН
# ==========================================
@router.message(F.text == "🎟 Создать Промокод")
async def admin_start_promo(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("Отправьте данные:\n`КОД, СУММА, КОЛИЧЕСТВО`")
    await state.set_state(PromoCreateStates.waiting_for_data)

@router.message(PromoCreateStates.waiting_for_data)
async def admin_save_promo(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split(",")
        code, reward, uses = parts[0].strip(), float(parts[1].strip()), int(parts[2].strip())
    except Exception:
        return await message.answer("❌ Ошибка парсинга.")

    async with db.pool.acquire() as conn:
        await conn.execute("INSERT INTO promocodes (code, reward, uses_left) VALUES ($1, $2, $3) ON CONFLICT (code) DO UPDATE SET reward = $2, uses_left = $3", code, reward, uses)
    await message.answer(f"✅ Промокод {code} создан!")
    await state.clear()

# ==========================================
# ИСПРАВЛЕННЫЙ РАСЧЕТ СТАВОК
# ==========================================
@router.message(F.text == "🏁 Завершить матч")
async def start_settle_match(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    async with db.pool.acquire() as conn:
        active_matches = await conn.fetch("SELECT id, title FROM matches WHERE status = 'active'")
    if not active_matches: return await message.answer("ℹ️ Нет активных матчей.")

    text = "🔎 **Выберите ID матча:**\n\n"
    for m in active_matches: text += f"• ID: `{m['id']}` — {m['title']}\n"
    await message.answer(text)
    await state.set_state(SettleMatchStates.match_id)

@router.message(SettleMatchStates.match_id)
async def process_settle_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(match_id=int(message.text))
    await message.answer("⚽️ Введите счет (например `2:0`):")
    await state.set_state(SettleMatchStates.score)

@router.message(SettleMatchStates.score)
async def process_settle_score(message: types.Message, state: FSMContext):
    clean_score = re.sub(r"[- ,._]", ":", message.text.strip())
    if not re.match(r"^\d+:\d+$", clean_score): return await message.answer("❌ Неверный формат.")
        
    data = await state.get_data()
    m_id = data['match_id']
    g1, g2 = map(int, clean_score.split(":"))

    # БРОНЕБОЙНЫЙ МАССИВ ИСХОДОВ (поддерживает и русский, и английский текст)
    winning = []
    winning.extend(["p1", "п1", "1"] if g1 > g2 else ["x", "х", "ничья"] if g1 == g2 else ["p2", "п2", "2"])
    
    if (g1 + g2) > 2.5: winning.extend(["tb", "tb2.5", "тб", "тб2.5", "тб 2.5"])
    else: winning.extend(["tm", "tm2.5", "тм", "тм2.5", "тм 2.5"])
        
    if g1 > 0 and g2 > 0: winning.extend(["oz", "oz_yes", "оз", "оз_да", "оз(да)", "оз да"])
    else: winning.extend(["oz_no", "оз_нет", "оз(нет)", "оз нет"])

    async with db.pool.acquire() as conn:
        match_info = await conn.fetchrow("SELECT title FROM matches WHERE id = $1", m_id)
        if not match_info: return await message.answer("❌ Матч не найден.")

        await conn.execute("UPDATE matches SET status = 'finished', score = $1 WHERE id = $2", clean_score, m_id)
        bets = await conn.fetch("SELECT * FROM bets WHERE status = 'pending' AND $1 = ANY(match_ids)", m_id)

        count = 0
        for b in bets:
            try:
                match_index = list(b['match_ids']).index(m_id)
                # Приводим ставку юзера к нижнему регистру для идеального совпадения
                user_outcome = str(b['outcomes'][match_index]).strip().lower()
            except (ValueError, IndexError):
                continue

            if user_outcome in winning:
                if len(b['match_ids']) == 1:
                    win_sum = b['amount'] * b['coef']
                    await conn.execute("UPDATE bets SET status = 'won' WHERE id = $1", b['id'])
                    await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", win_sum, b['user_id'])
                    try: await message.bot.send_message(b['user_id'], f"🟢 Ставка №{b['id']} выиграла!\nМатч: {match_info['title']} ({clean_score})\n💰 +{round(win_sum, 1)} ⭐️")
                    except Exception: pass
                else:
                    all_finished = True
                    for m_in_bet in b['match_ids']:
                        m_stat = await conn.fetchval("SELECT status FROM matches WHERE id = $1", m_in_bet)
                        if m_stat != 'finished': all_finished = False
                    
                    if all_finished:
                        win_sum = b['amount'] * b['coef']
                        await conn.execute("UPDATE bets SET status = 'won' WHERE id = $1", b['id'])
                        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", win_sum, b['user_id'])
                        try: await message.bot.send_message(b['user_id'], f"🎉 Экспресс №{b['id']} СЫГРАЛ!\n💰 +{round(win_sum, 1)} ⭐️")
                        except Exception: pass
            else:
                await conn.execute("UPDATE bets SET status = 'lost' WHERE id = $1", b['id'])
                try: await message.bot.send_message(b['user_id'], f"🔴 Ставка №{b['id']} проиграла.\nМатч: {match_info['title']} ({clean_score})")
                except Exception: pass
            count += 1

        remaining = await conn.fetchval("SELECT COUNT(*) FROM matches WHERE status = 'active'")
        if remaining == 0: await conn.execute("UPDATE bot_settings SET value = 'false' WHERE key = 'bets_locked'")
            
    await message.answer(f"🏁 Матч {match_info['title']} закрыт. Рассчитано купонов: {count}.")
    await state.clear()

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
    if len(args) < 3: return
    target, amount = int(args[1]), float(args[2])
    async with db.pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, target)
    await message.answer(f"💰 Выдано +{amount} ⭐️ игроку `{target}`.")
