import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command  # Правильный импорт фильтра команд для aiogram 3.x
from database import db

# Инициализируем роутер админа
router = Router()
logger = logging.getLogger(__name__)

# Стейты для пошагового сбора данных о матче
class AutoMatchStates(StatesGroup):
    team1_data = State()
    team2_data = State()


def clip_coef(val: float) -> float:
    """Вспомогательная функция, чтобы коэффициенты не улетали ниже 1.15 и выше 7.50"""
    return max(1.15, min(7.50, val))


def parse_team_form(scores_str: str) -> dict:
    """
    Парсит строку с результатами (например, '2:1 1:1 0:3'),
    считает очки, забитые/пропущенные голы и ОЗ (Обе Забьют).
    """
    scores = scores_str.strip().split()
    goals_scored = 0
    goals_conceded = 0
    points = 0
    btts_count = 0  # Количество матчей, где обе забили
    total_matches = 0

    for s in scores:
        if ":" in s:
            try:
                g1, g2 = map(int, s.split(":"))
                goals_scored += g1
                goals_conceded += g2
                total_matches += 1
                
                # Считаем очки формы
                if g1 > g2:
                    points += 3
                elif g1 == g2:
                    points += 1
                
                # Проверяем Обе Забьют
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
# ХЕНДЛЕРЫ: АВТОМАТИЧЕСКОЕ СОЗДАНИЕ МАТЧА
# ==========================================

# 1. Точка входа: команда /add_auto или текстовая кнопка
@router.message(Command("add_auto"))
@router.message(F.text == "➕ Авто-матч")
async def start_auto_match(message: types.Message, state: FSMContext):
    text = (
        "⚽️ **Автогенерация матча по форме команд**\n\n"
        "Введите **НАЗВАНИЕ первой команды** и **3 последних счета** через запятую.\n\n"
        "📝 **Пример ввода:**\n`МФЛ Старс, 2:1 1:1 3:0`"
    )
    await message.answer(text, parse_mode="Markdown")
    await state.set_state(AutoMatchStates.team1_data)


# 2. Обработка данных Первой Команды (Хозяева)
@router.message(AutoMatchStates.team1_data)
async def process_team1(message: types.Message, state: FSMContext):
    if "," not in message.text:
        await message.answer(
            "❌ **Неверный формат!** Обязательно разделяйте название и счета запятой.\n"
            "Попробуйте еще раз:\n`Ювентус, 1:0 2:2 0:1`", 
            parse_mode="Markdown"
        )
        return

    try:
        name, scores = message.text.split(",", 1)
        stats = parse_team_form(scores)
        
        # Сохраняем во внутренний буфер FSM
        await state.update_data(t1_name=name.strip(), t1_stats=stats)
        
        text = (
            f"✅ Первая команда **{name.strip()}** успешно сохранена.\n\n"
            f"Теперь введите **НАЗВАНИЕ второй команды** (Гости) и 3 её матча через запятую:\n"
            f"📝 **Пример ввода:**\n`ФТКЛ Юнайтед, 1:2 0:0 4:1`"
        )
        await message.answer(text, parse_mode="Markdown")
        await state.set_state(AutoMatchStates.team2_data)
        
    except Exception as e:
        logger.error(f"Ошибка при парсинге команды 1: {e}")
        await message.answer("❌ Произошла ошибка при обработке текста. Проверьте формат и введите заново.")


# 3. Обработка данных Второй Команды (Гости) + Расчет + Сохранение в БД
@router.message(AutoMatchStates.team2_data)
async def process_team2(message: types.Message, state: FSMContext):
    if "," not in message.text:
        await message.answer(
            "❌ **Неверный формат!** Обязательно разделяйте название и счета запятой.\n"
            "Попробуйте еще раз:\n`Реал Мадрид, 1:2 0:0 4:1`", 
            parse_mode="Markdown"
        )
        return

    try:
        name2, scores2 = message.text.split(",", 1)
        stats2 = parse_team_form(scores2)
        name2 = name2.strip()

        # Достаем из памяти данные первой команды
        user_data = await state.get_data()
        name1 = user_data['t1_name']
        stats1 = user_data['t1_stats']

        # --- МАТЕМАТИЧЕСКИЙ РАСЧЕТ СИЛЫ КОМАНД ---
        # Сила = Очки + (Разница мячей * 0.5) + Базовый коэффициент 5
        strength1 = stats1['points'] + (stats1['scored'] - stats1['conceded']) * 0.5 + 5
        strength2 = stats2['points'] + (stats2['scored'] - stats2['conceded']) * 0.5 + 5
        
        # Защита от нулевой или отрицательной силы
        strength1 = max(1.0, strength1)
        strength2 = max(1.0, strength2)
        
        total_strength = strength1 + strength2
        
        # Маржа букмекера (8%), чистая вероятность распределяется на исходы
        margin = 0.92
        prob_p1 = (strength1 / total_strength) * 0.72
        prob_p2 = (strength2 / total_strength) * 0.72
        prob_x = 0.28  # Базовый шанс ничьей в футболе ~28%
        
        # Рассчитываем кэфы основных исходов (П1, Х, П2)
        coef_p1 = round(clip_coef(1 / (prob_p1 * margin)), 2)
        coef_p2 = round(clip_coef(1 / (prob_p2 * margin)), 2)
        coef_x = round(clip_coef(1 / (prob_x * margin)), 2)

        # Расчет Тоталов (ТБ 2.5 / ТМ 2.5) по средней результативности команд
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
        btts_prob = max(0.2, min(0.8, btts_prob)) 
        
        coef_oz_yes = round(clip_coef(1 / (btts_prob * margin)), 2)
        coef_oz_no = round(clip_coef(1 / ((1 - btts_prob) * margin)), 2)

        # --- СОХРАНЕНИЕ МАТЧА В ПОСТГРЕС ---
        match_title = f"{name1} — {name2}"
        
        async with db.pool.acquire() as conn:
            await conn.execute(
                '''INSERT INTO matches (title, coef_p1, coef_x, coef_p2, coef_tb, coef_tm, coef_oz_yes, coef_oz_no, status) 
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'active')''',
                match_title, coef_p1, coef_x, coef_p2, coef_tb, coef_tm, coef_oz_yes, coef_oz_no
            )

        # Вывод результатов админу в чат
        success_text = (
            f"🎉 **Матч успешно добавлен в систему!**\n\n"
            f"🏆 **{match_title}**\n"
            f"📊 **Сгенерированные аналитикой коэффициенты:**\n"
            f"• **П1**: `{coef_p1}` | **Х**: `{coef_x}` | **П2**: `{coef_p2}`\n"
            f"• **ТБ (2.5)**: `{coef_tb}` | **ТМ (2.5)**: `{coef_tm}`\n"
            f"• **ОЗ (Да)**: `{coef_oz_yes}` | **ОЗ (Нет)**: `{coef_oz_no}`\n\n"
            f"📱 Игроки уже могут делать ставки через меню матчей!"
        )
        await message.answer(success_text, parse_mode="Markdown")
        
        # Сбрасываем состояние FSM, чтобы бот вышел из режима ожидания ввода
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка при создании авто-матча: {e}", exc_info=True)
        await message.answer("❌ Произошла критическая ошибка при записи матча в базу данных. Попробуйте позже.")
        await state.clear()
