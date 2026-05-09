import asyncio

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

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()


@dp.message(F.text == "/start")
async def start(message: Message):

    await create_user(message.from_user.id)

    await message.answer(
        "Добро пожаловать в MIFL BET ⚽",
        reply_markup=main_keyboard
    )


@dp.message(F.text == "👤 Профиль")
async def profile(message: Message):

    user = await get_user(message.from_user.id)

    await message.answer(f"""
👤 Профиль

💰 Баланс: {user['balance']}
""")


@dp.message(F.text == "⚽ Матчи")
async def matches(message: Message):

    matches = await get_matches()

    if not matches:
        await message.answer("Матчей пока нет.")
        return

    for match in matches:

        text = f"""
🏟️ {match['home_team']} vs {match['away_team']}

П1 — {match['odds_home']}
X — {match['odds_draw']}
П2 — {match['odds_away']}

ТБ 2.5 — {match['odds_over25']}
ТМ 2.5 — {match['odds_under25']}

ОЗ Да — {match['odds_btts_yes']}
ОЗ Нет — {match['odds_btts_no']}
"""

        await message.answer(
            text,
            reply_markup=betting_keyboard(match['id'])
        )


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


@dp.message(BetState.waiting_for_amount)
async def process_bet(
    message: Message,
    state: FSMContext
):

    amount = int(message.text)

    user = await get_user(
        message.from_user.id
    )

    if user['balance'] < amount:

        await message.answer(
            "Недостаточно средств."
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

    await message.answer(f"""
✅ Ставка принята

💰 Сумма: {amount}
📈 Коэффициент: {odds}
🎯 Исход: {prediction}
""")

    await state.clear()


async def seed_match():

    matches = await get_matches()

    if matches:
        return

    odds = calculate_odds(
        85,
        79,
        8,
        5
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


async def main():

    await connect_db()

    await init_db()

    await seed_match()

    print("MIFL BET started")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
