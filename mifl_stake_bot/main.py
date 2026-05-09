import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

from config import BOT_TOKEN

from database import (
    connect_db,
    init_db,

    create_user,
    get_user,

    create_match,
    get_matches
)

from keyboards import main_keyboard

from odds_engine import calculate_odds

from ai_analysis import generate_analysis

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
👤 Ваш профиль

💰 Баланс: {user['balance']}
""")


@dp.message(F.text == "⚽ Матчи")
async def matches(message: Message):

    matches = await get_matches()

    if not matches:
        await message.answer("Матчей пока нет.")
        return

    text = "⚽ Матчи MIFL\n"

    for match in matches:

        text += f"""

🏟️ {match['home_team']} vs {match['away_team']}

П1 — {match['odds_home']}
X — {match['odds_draw']}
П2 — {match['odds_away']}

"""

        analysis = generate_analysis(
            match['home_team'],
            match['away_team'],
            match['home_rating'],
            match['away_rating'],
            match['home_form'],
            match['away_form']
        )

        text += analysis
        text += "\n━━━━━━━━━━━━\n"

    await message.answer(text)


async def seed_matches():

    matches = await get_matches()

    if matches:
        return

    odds = calculate_odds(
        home_rating=85,
        away_rating=78,
        home_form=8,
        away_form=5
    )

    await create_match(
        home_team="Phoenix",
        away_team="Titans",

        home_rating=85,
        away_rating=78,

        home_form=8,
        away_form=5,

        odds_home=odds["home"],
        odds_draw=odds["draw"],
        odds_away=odds["away"]
    )


async def main():

    await connect_db()

    await init_db()

    await seed_matches()

    print("MIFL BET started")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
