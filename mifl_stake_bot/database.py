import asyncpg
import logging

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self, db_url: str):
        try:
            self.pool = await asyncpg.create_pool(db_url)
            logging.info("Подключение к БД успешно.")
            await self.create_tables()
        except Exception as e:
            logging.error(f"Ошибка подключения к БД: {e}")

    async def create_tables(self):
        query = """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            balance NUMERIC DEFAULT 1000.0
        );

        CREATE TABLE IF NOT EXISTS matches (
            match_id SERIAL PRIMARY KEY,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            score TEXT DEFAULT 'X:X'
        );

        CREATE TABLE IF NOT EXISTS bets (
            bet_id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id),
            match_id INTEGER REFERENCES matches(match_id),
            bet_type TEXT,
            amount NUMERIC,
            odds NUMERIC,
            status TEXT DEFAULT 'active'
        );
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query)
            logging.info("Таблицы успешно проверены/созданы.")

    async def add_user_if_not_exists(self, user_id: int, username: str):
        query = """
        INSERT INTO users (user_id, username) 
        VALUES ($1, $2) 
        ON CONFLICT (user_id) DO NOTHING;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, username)

# Единый экземпляр для всего проекта
db = Database()
