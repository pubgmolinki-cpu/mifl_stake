import asyncpg

from config import DATABASE_URL

pool = None


async def connect_db():
    global pool

    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10
    )


async def init_db():

    async with pool.acquire() as conn:

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            balance INTEGER DEFAULT 1000
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id SERIAL PRIMARY KEY,

            home_team TEXT,
            away_team TEXT,

            home_rating INTEGER,
            away_rating INTEGER,

            home_form INTEGER,
            away_form INTEGER,

            odds_home REAL,
            odds_draw REAL,
            odds_away REAL,

            status TEXT DEFAULT 'upcoming',

            home_score INTEGER,
            away_score INTEGER
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id SERIAL PRIMARY KEY,

            user_id BIGINT,
            match_id INTEGER,

            bet_type TEXT,
            prediction TEXT,

            amount INTEGER,
            odds REAL,

            status TEXT DEFAULT 'pending'
        )
        """)


async def create_user(telegram_id: int):

    async with pool.acquire() as conn:

        exists = await conn.fetchrow("""
        SELECT * FROM users
        WHERE telegram_id = $1
        """, telegram_id)

        if not exists:

            await conn.execute("""
            INSERT INTO users (telegram_id)
            VALUES ($1)
            """, telegram_id)


async def get_user(telegram_id: int):

    async with pool.acquire() as conn:

        user = await conn.fetchrow("""
        SELECT * FROM users
        WHERE telegram_id = $1
        """, telegram_id)

        return user


async def create_match(
    home_team,
    away_team,
    home_rating,
    away_rating,
    home_form,
    away_form,
    odds_home,
    odds_draw,
    odds_away
):

    async with pool.acquire() as conn:

        await conn.execute("""
        INSERT INTO matches (
            home_team,
            away_team,

            home_rating,
            away_rating,

            home_form,
            away_form,

            odds_home,
            odds_draw,
            odds_away
        )
        VALUES (
            $1, $2,
            $3, $4,
            $5, $6,
            $7, $8, $9
        )
        """,
        home_team,
        away_team,

        home_rating,
        away_rating,

        home_form,
        away_form,

        odds_home,
        odds_draw,
        odds_away
        )


async def get_matches():

    async with pool.acquire() as conn:

        matches = await conn.fetch("""
        SELECT *
        FROM matches
        WHERE status = 'upcoming'
        """)

        return matches
