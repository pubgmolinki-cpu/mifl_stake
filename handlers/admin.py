from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db
import logging

# Оставляем старый роутер или используем текущий из admin.py
router = Router() 

# Состояния для пошагового ввода данных
class AutoMatchStates(StatesGroup):
    team1_data = State()
    team2_data = State()

# Функция парсинга результатов матчей (считает очки, голы и ОЗ)
def parse_team_form(scores_str: str):
    scores = scores_str.strip().split()
    goals_scored = 0
    goals_conceded = 0
    points = 0
    btts_count = 0  # Сколько раз обе забили
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

# 1. Начало процесса автоматического создания матча
@router.message(F.text == "➕ Авто-матч")
@router.message(commands=["add_auto"])
async def start_auto_match(message: types.Message, state: FSMContext):
    # Тут можно добавить проверку на админа (например: if message.from_user.id not in ADMIN_IDS)
    text = (
        "⚽️ **Автогенерация матча по форме команд**\n\n"
        "Введите НАЗВАНИЕ первой команды и 3 последних счета через запятую.\n"
        "**Пример:** `Барселона, 2:1 1:1 3:0`"
    )
    await message.answer(text, parse_mode="Markdown")
    await state.set_state(AutoMatchStates.team1_data)

# 2. Ловим данные первой команды
@router.message(AutoMatchStates.team1_data)
async def process_team1(message: types.Message, state: FSMContext):
    if "," not in message.text:
        await message.answer("❌ Неверный формат. Обязательно ставьте запятую!\nПример: `Ювентус, 1:0 2:2 0:1`")
        return

    name, scores = message.text.split(",", 1)
    stats = parse_team_form(scores)
    
    await state.update_data(t1_name=name.strip(), t1_stats=stats)
    
    await message.answer(
        f"✅ Первая команда **{name.strip()}** сохранена.\n"
        f"Теперь введите НАЗВАНИЕ второй команды и 3 её матча через запятую:\n"
        f"**Пример:** `Реал Мадрид, 1:2 0:0 4:1`",
        parse_mode="Markdown"
    )
    await state.set_state(AutoMatchStates.team2_data)

# 3. Ловим данные второй команды, считаем кэфы и сохраняем матч
@router.message(AutoMatchStates.team2_data)
async def process_team2(message: types.Message, state: FSMContext):
    if "," not in message.text:
        await message.answer("❌ Неверный формат. Обязательно ставьте запятую!\nПример: `Реал Мадрид, 1:2 0:0 4:1`")
        return

    name2, scores2 = message.text.split(",", 1)
    stats2 = parse_team_form(scores2)
    
    data = await state.get_data()
    name1 = data['t1_name']
    stats1 = data['t1_stats']
    name2 = name2.strip()

    # --- МАТЕМАТИЧЕСКИЙ РАСЧЕТ КОЭФФИЦИЕНТОВ ---
    # Сила команды базируется на очках формы и разнице мячей
    strength1 = stats1['points'] + (stats1['scored'] - stats1['conceded']) * 0.5 + 5
    strength2 = stats2['points'] + (stats2['scored'] - stats2['conceded']) * 0.5 + 5
    
    # Ограничиваем минимальную силу, чтобы избежать деления на ноль
    strength1 = max(1.0, strength1)
    strength2 = max(1.0, strength2)
    
    total_strength = strength1 + strength2
    
    # Базовые вероятности исходов (с учетом маржи букмекера 8%)
    margin = 0.92
    prob_p1 = (strength1 / total_strength) * 0.72
    prob_p2 = (strength2 / total_strength) * 0.72
    prob_x = 0.28  # Вероятность ничьей базово 28%
    
    # Рассчитываем кэфы на исходы (с границами от 1.15 до 8.0)
    coef_p1 = round(clip_coef(1 / (prob_p1 * margin)), 2)
    coef_p2 = round(clip_coef(1 / (prob_p2 * margin)), 2)
    coef_x = round(clip_coef(1 / (prob_x * margin)), 2)

    # Расчет Тоталов (ТБ 2.5 / ТМ 2.5) на основе средней результативности
    avg_goals = ((stats1['scored'] + stats1['conceded']) / stats1['matches'] + 
                 (stats2['scored'] + stats2['conceded']) / stats2['matches']) / 2
                 
    if avg_goals >= 2.5:
        coef_tb = round(clip_coef(1.5 + (4.0 - avg_goals) * 0.2), 2)
        coef_tm = round(clip_coef(2.3 + (avg_goals - 2.5) * 0.3), 2)
    else:
        coef_tb = round(clip_coef(2.2 + (2.5 - avg_goals) * 0.3), 2)
        coef_tm = round(clip_coef(1.6 + (avg_goals - 1.0) * 0.2), 2)

    # Расчет Обе Забьют (ОЗ Да / ОЗ Нет)
    btts_prob = (stats1['btts'] / stats1['matches'] + stats2['btts'] / stats2['matches']) / 2
    btts_prob = max(0.2, min(0.8, btts_prob)) # Защита от экстремальных значений
    
    coef_oz_yes = round(clip_coef(1 / (btts_prob * margin)), 2)
    coef_oz_no = round(clip_coef(1 / ((1 - btts_prob) * margin)), 2)

    # --- ЗАПИСЬ В БАЗУ ДАННЫХ ---
    match_title = f"{name1} — {name2}"
    
    async with db.pool.acquire() as conn:
        await conn.execute(
            '''INSERT INTO matches (title, coef_p1, coef_x, coef_p2, coef_tb, coef_tm, coef_oz_yes, coef_oz_no, status) 
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'active')''',
            match_title, coef_p1, coef_x, coef_p2, coef_tb, coef_tm, coef_oz_yes, coef_oz_no
        )

    # Красивый вывод результата админу
    success_text = (
        f"🎉 **Матч успешно сгенерирован и добавлен!**\n\n"
        f"🏆 **{match_title}**\n"
        f"📊 Расчитанные коэффициенты:\n"
        f"• **П1**: {coef_p1} | **Х**: {coef_x} | **П2**: {coef_p2}\n"
        f"• **ТБ (2.5)**: {coef_tb} | **ТМ (2.5)**: {coef_tm}\n"
        f"• **ОЗ (Да)**: {coef_oz_yes} | **ОЗ (Нет)**: {coef_oz_no}"
    )
    await message.answer(success_text, parse_mode="Markdown")
    await state.clear()

# Вспомогательная функция, чтобы кэфы не улетали в космос
def clip_coef(val):
    return max(1.15, min(7.50, val))
