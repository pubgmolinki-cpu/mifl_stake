import os
import logging
import asyncio
import asyncpg

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        # Берем URL подключения к базе из переменных окружения (например, на Render или Railway)
        self.db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
        self.pool = None

    async def connect(self):
        """Создает пул подключений к базе данных PostgreSQL и проверяет таблицы"""
        try:
            self.pool = await asyncpg.create_pool(self.db_url)
            logger.info("Успешное подключение к пулу базы данных PostgreSQL.")
            
            # Автоматическая инициализация и обновление таблиц под новый функционал
            async with self.pool.acquire() as conn:
                # Таблица пользователей
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        balance TEXT DEFAULT '1000.0',
                        last_bonus TIMESTAMP DEFAULT NULL
                    );
                ''')
                
                # Переводим balance на NUMERIC, если он вдруг был создан как TEXT
                try:
                    await conn.execute("ALTER TABLE users ALTER COLUMN balance TYPE NUMERIC USING balance::numeric;")
                except Exception:
                    pass
                
                # Добавляем колонку времени бонуса на случай, если таблица уже существовала без неё
                await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_bonus TIMESTAMP DEFAULT NULL;")

                # Таблица футбольных матчей
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS matches (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT EXISTS UNIQUE,
                        coef_p1 NUMERIC,
                        coef_x NUMERIC,
                        coef_p2 NUMERIC,
                        coef_tb NUMERIC,
                        coef_tm NUMERIC,
                        coef_oz_yes NUMERIC,
                        coef_oz_no NUMERIC,
                        status TEXT DEFAULT 'active'
                    );
                ''')
                try:
                    await conn.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS title TEXT;")
                except Exception: pass

                # Таблица интерактивных ставок
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS interactive_bets (
                        id SERIAL PRIMARY KEY,
                        title TEXT,
                        options JSONB,
                        status TEXT DEFAULT 'active'
                    );
                ''')

                # Таблица купонов ставок игроков
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS bets (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        match_ids INT[],
                        outcomes TEXT[],
                        coef NUMERIC,
                        amount NUMERIC,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                
            logger.info("Все таблицы базы данных успешно проверены и обновлены.")
        except Exception as e:
            logger.critical(f"Критическая ошибка при инициализации базы данных: {e}", exc_info=True)
            raise e

# Экспортируем глобальный объект базы данных
db = Database()
