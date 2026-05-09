import asyncpg

from config import DATABASE_URL

pool = None


# =========================
# CONNECT DATABASE
# =========================

async def connect_db():

    global pool

    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10
    )


# =========================
# INIT DATABASE
# =========================

async def init_db():

    async with pool.acquire() as conn:

        # =========================
        # DROP OLD TABLES (MVP)
        # =========================

        await conn.execute("""
        DROP TABLE IF EXISTS bets CASCADE
        """)

        await conn.execute("""
        DROP TABLE IF EXISTS matches CASCADE
        """)

        await conn.execute("""
        DROP TABLE IF EXISTS users CASCADE
        """)

        # =========================
        # USERS
        # =========================

        await conn.execute("""
        CREATE TABLE users (

            id SERIAL PRIMARY KEY,

            telegram_id BIGINT UNIQUE,

            balance INTEGER DEFAULT 1000

        )
        """)

        # =========================
        # MATCHES
        # =========================

        await conn.execute("""
        CREATE TABLE matches (

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

            odds_over25 REAL,
            odds_under25 REAL,

            odds_btts_yes REAL,
            odds_btts_no REAL,

            status TEXT DEFAULT 'upcoming',

            home_score INTEGER,
            away_score INTEGER

        )
        """)

        # =========================
        # BETS
        # =========================

        await conn.execute("""
        CREATE TABLE bets (

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

        print("✅ Таблицы успешно созданы")


# =========================
# USERS
# =========================

async def create_user(telegram_id):

    async with pool.acquire() as conn:

        user = await conn.fetchrow("""
        SELECT *
        FROM users
        WHERE telegram_id = $1
        """, telegram_id)

        if not user:

            await conn.execute("""
            INSERT INTO users (telegram_id)
            VALUES ($1)
            """, telegram_id)


async def get_user(telegram_id):

    async with pool.acquire() as conn:

        return await conn.fetchrow("""
        SELECT *
        FROM users
        WHERE telegram_id = $1
        """, telegram_id)


async def update_balance(
    telegram_id,
    amount
):

    async with pool.acquire() as conn:

        await conn.execute("""
        UPDATE users
        SET balance = balance + $1
        WHERE telegram_id = $2
        """,
        amount,
        telegram_id
        )


# =========================
# MATCHES
# =========================

async def create_match(

    home_team,
    away_team,

    home_rating,
    away_rating,

    home_form,
    away_form,

    odds_home,
    odds_draw,
    odds_away,

    odds_over25,
    odds_under25,

    odds_btts_yes,
    odds_btts_no
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
            odds_away,

            odds_over25,
            odds_under25,

            odds_btts_yes,
            odds_btts_no

        )

        VALUES (

            $1, $2,
            $3, $4,
            $5, $6,
            $7, $8, $9,
            $10, $11,
            $12, $13

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
        odds_away,

        odds_over25,
        odds_under25,

        odds_btts_yes,
        odds_btts_no
        )


async def get_matches():

    async with pool.acquire() as conn:

        return await conn.fetch("""
        SELECT *
        FROM matches
        WHERE status = 'upcoming'
        """)


async def get_match(match_id):

    async with pool.acquire() as conn:

        return await conn.fetchrow("""
        SELECT *
        FROM matches
        WHERE id = $1
        """, match_id)


# =========================
# BETS
# =========================

async def create_bet(

    user_id,
    match_id,

    bet_type,

    prediction,

    amount,
    odds
):

    async with pool.acquire() as conn:

        await conn.execute("""
        INSERT INTO bets (

            user_id,
            match_id,

            bet_type,

            prediction,

            amount,
            odds

        )

        VALUES (

            $1,
            $2,

            $3,

            $4,

            $5,
            $6

        )
        """,

        user_id,
        match_id,

        bet_type,

        prediction,

        amount,
        odds
        )


async def get_user_bets(user_id):

    async with pool.acquire() as conn:

        return await conn.fetch("""
        SELECT *
        FROM bets
        WHERE user_id = $1
        ORDER BY id DESC
        """, user_id)
