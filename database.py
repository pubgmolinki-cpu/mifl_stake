import asyncpg
from config import DATABASE_URL
from datetime import datetime

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(dsn=DATABASE_URL)
            await self.create_tables()

    async def create_tables(self):
        async with self.pool.acquire() as conn:
            # Таблица пользователей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    tg_id BIGINT PRIMARY KEY,
                    username TEXT,
                    balance INT DEFAULT 1000,
                    referrer_id BIGINT,
                    last_bonus TIMESTAMP
                );
            ''')
            # Таблица матчей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS matches (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT EXISTS,
                    coef_p1 REAL, coef_x REAL, coef_p2 REAL,
                    coef_tb REAL, coef_tm REAL,
                    coef_oz_yes REAL, coef_oz_no REAL,
                    status TEXT DEFAULT 'active'
                );
            ''')
            # Таблица ставок (поддерживает и ординары, и экспрессы через массивы)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bets (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    match_ids INT[],
                    outcomes TEXT[],
                    bet_type TEXT,
                    amount INT,
                    total_coef REAL,
                    status TEXT DEFAULT 'pending'
                );
            ''')

    # Взаимодействие с юзерами
    async def get_user(self, tg_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", tg_id)

    async def register_user(self, tg_id, username, referrer_id=None):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (tg_id, username, referrer_id) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                tg_id, username, referrer_id
            )

    async def update_balance(self, tg_id, amount):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET balance = balance + $1 WHERE tg_id = $2", amount, tg_id)

    async def get_top_users(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10")

    async def get_user_rank(self, tg_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT row_number FROM (
                    SELECT tg_id, ROW_NUMBER() OVER (ORDER BY balance DESC) as row_number FROM users
                ) t WHERE tg_id = $1
            """, tg_id)
            return row['row_number'] if row else 0

    # Взаимодействие с матчами и ставками
    async def add_match(self, title, p1, x, p2, tb, tm, oz_y, oz_n):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO matches (title, coef_p1, coef_x, coef_p2, coef_tb, coef_tm, coef_oz_yes, coef_oz_no) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                title, p1, x, p2, tb, tm, oz_y, oz_n
            )

    async def get_active_matches(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM matches WHERE status = 'active'")

    async def add_bet(self, user_id, match_ids, outcomes, bet_type, amount, total_coef):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO bets (user_id, match_ids, outcomes, bet_type, amount, total_coef) VALUES ($1, $2, $3, $4, $5, $6)",
                user_id, match_ids, outcomes, bet_type, amount, total_coef
            )

    async def get_user_bets(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM bets WHERE user_id = $1 ORDER BY id DESC", user_id)

db = Database()
