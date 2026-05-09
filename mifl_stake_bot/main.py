import asyncio
import os

from threading import Thread

from flask import Flask

from aiogram import (
    Bot,
    Dispatcher,
    F
)

from aiogram.types import (
    Message,
    CallbackQuery
)

from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN

from database import *

from keyboards import main_keyboard

from odds_engine import calculate_odds

from betting import betting_keyboard

from states import BetState


# =========================
# FLASK
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "MIFL BET BOT WORKING"


def run_web():
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================
# TELEGRAM BOT
# =========================

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()


# =========================
# START
# =========================

@dp.message(F.text == "/start")
async def start(message: Message):

    await create_user(message.from_user.id)

    await message.answer(
        "Добро пожаловать в MIFL BET ⚽",
        reply_markup=main_keyboard
    )


# =========================
# PROFILE
# =========================

@dp.message(F.text == "👤 Профиль")
async def profile(message: Message):

    user = await get_user(message.from_user.id)

    await message.answer(f"""
👤 Профиль

💰 Баланс: {user['balance']}
""")


# =========================
# MATCHES
# =========================

@dp.message(F.text == "⚽ Матчи")
async def matches(message: Message):

    matches = await get_matches()

    if not matches:

        await message.answer(
            "Матчей пока нет."
        )

        return

    for match in matches:

        text = f"""
🏟️ {match['home_team']} vs {match['away_team']}

📈 Коэффициенты:

П1 — {match['odds_home']}
X — {match['odds_draw']}
П2 — {match['odds_away']}

⚽ Тоталы:

ТБ 2.5 — {match['odds_over25']}
ТМ 2.5 — {match['odds_under25']}

🔥 Обе Забьют:

ОЗ Да — {match['odds_btts_yes']}
ОЗ Нет — {match['odds_btts_no']}
"""

        await message.answer(
            text,
            reply_markup=betting_keyboard(match['id'])
        )


# =========================
# BET BUTTON CLICK
# =========================

@dp.callback_query(F.data.startswith("bet"))
async def bet_handler(
    callback: CallbackQuery,
    state: FSMContext
):

    _, match_id, prediction = callback.data.split(":")

    await state.update_data(
        match_id=int(match_id),
        prediction=prediction
    )

    await callback.message.answer(
        "Введите сумму ставки:"
    )

    await state.set_state(
        BetState.waiting_for_amount
    )

    await callback.answer()


# =========================
# PROCESS BET
# =========================

@dp.message(BetState.waiting_for_amount)
async def process_bet(
    message: Message,
    state: FSMContext
):

    if not message.text.isdigit():

        await message.answer(
            "Введите корректное число."
        )

        return

    amount = int(message.text)

    if amount <= 0:

        await message.answer(
            "Сумма должна быть больше 0."
        )

        return

    user = await get_user(
        message.from_user.id
    )

    if user['balance'] < amount:

        await message.answer(
            "❌ Недостаточно средств."
        )

        return

    data = await state.get_data()

    match = await get_match(
        data['match_id']
    )

    prediction = data['prediction']

    odds_map = {

        "П1": match['odds_home'],
        "X": match['odds_draw'],
        "П2": match['odds_away'],

        "OVER": match['odds_over25'],
        "UNDER": match['odds_under25'],

        "BTTS_YES": match['odds_btts_yes'],
        "BTTS_NO": match['odds_btts_no']
    }

    odds = odds_map[prediction]

    await update_balance(
        message.from_user.id,
        -amount
    )

    await create_bet(
        user_id=message.from_user.id,
        match_id=data['match_id'],
        bet_type="single",
        prediction=prediction,
        amount=amount,
        odds=odds
    )

    possible_win = round(
        amount * odds,
        2
    )

    await message.answer(f"""
✅ Ставка успешно принята

💰 Сумма: {amount}

📈 Коэффициент: {odds}

🎯 Исход: {prediction}

🏆 Возможный выигрыш:
{possible_win}
""")

    await state.clear()


# =========================
# SEED MATCH
# =========================

async def seed_match():

    matches = await get_matches()

    if matches:
        return

    odds = calculate_odds(
        home_rating=85,
        away_rating=79,
        home_form=8,
        away_form=5
    )

    await create_match(
        "Phoenix",
        "Titans",

        85,
        79,

        8,
        5,

        odds["home"],
        odds["draw"],
        odds["away"],

        odds["over25"],
        odds["under25"],

        odds["btts_yes"],
        odds["btts_no"]
    )


# =========================
# MAIN
# =========================

async def main():

    print("🔌 Подключение к БД...")

    await connect_db()

    print("✅ БД подключена")

    await init_db()

    print("✅ Таблицы проверены")

    await seed_match()

    print("✅ Тестовый матч создан")

    Thread(target=run_web).start()

    print("🌐 Flask server started")

    print("🤖 MIFL BET BOT STARTED")

    await dp.start_polling(bot)


# =========================
# RUN
# =========================

if __name__ == "__main__":
    asyncio.run(main())
