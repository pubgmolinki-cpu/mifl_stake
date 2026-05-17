import os
import logging
import asyncpg

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
        self.pool = None

    async def connect(self):
        try:
            self.pool = await asyncpg.create_pool(self.db_url)
            logger.info("Успешное подключение к базе данных PostgreSQL.")
            
            async with self.pool.acquire() as conn:
                # 1. Таблица пользователей
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        balance NUMERIC DEFAULT 1000.0,
                        last_bonus TIMESTAMP DEFAULT NULL,
                        referred_by BIGINT DEFAULT NULL
                    );
                ''')
                await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT DEFAULT NULL;")

                # 2. Таблица футбольных матчей
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS matches (
                        id SERIAL PRIMARY KEY,
                        title TEXT UNIQUE,
                        coef_p1 NUMERIC,
                        coef_x NUMERIC,
                        coef_p2 NUMERIC,
                        coef_tb NUMERIC,
                        coef_tm NUMERIC,
                        coef_oz_yes NUMERIC,
                        coef_oz_no NUMERIC,
                        status TEXT DEFAULT 'active',
                        score TEXT DEFAULT NULL
                    );
                ''')
                # АВТО-МИГРАЦИЯ: Добавляем колонку score для хранения результатов матчей (3:1, 0:2 и т.д.)
                await conn.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS score TEXT DEFAULT NULL;")

                # 3. Таблица промокодов
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS promocodes (
                        code TEXT PRIMARY KEY,
                        reward NUMERIC,
                        uses_left INT
                    );
                ''')

                # 4. Связующая таблица промокодов
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_promos (
                        user_id BIGINT,
                        code TEXT,
                        PRIMARY KEY (user_id, code)
                    );
                ''')

                # 5. Таблица купонов ставок (твоя старая структура)
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
                
                # АВТО-МИГРАЦИЯ: Добавляем колонки массивов для поддержки экспрессов в старой БД
                await conn.execute("ALTER TABLE bets ADD COLUMN IF NOT EXISTS match_ids INT[];")
                await conn.execute("ALTER TABLE bets ADD COLUMN IF NOT EXISTS outcomes TEXT[];")

                # =====================================================================
                # НОВЫЕ ТАБЛИЦЫ ДЛЯ ПОЛНОЙ СОВМЕСТИМОСТИ С ОБНОВЛЕННЫМИ ХЕНДЛЕРАМИ
                # =====================================================================

                # 6. Таблица системных настроек (для глобальной заморозки ставок админом)
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS bot_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    );
                ''')
                
                # Записываем дефолтное состояние заморозки (по умолчанию ставки открыты)
                await conn.execute('''
                    INSERT INTO bot_settings (key, value) 
                    VALUES ('bets_locked', 'false') 
                    ON CONFLICT (key) DO NOTHING;
                ''')

                # 7. Таблица одиночных ставок (single_bets) для нового обработчика
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS single_bets (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        match_id BIGINT,
                        outcome TEXT,
                        amount NUMERIC,
                        coef NUMERIC,
                        status TEXT DEFAULT 'pending'
                    );
                ''')

                # 8. Таблица экспресс ставок (express_bets) для нового обработчика
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS express_bets (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        matches_data TEXT,
                        amount NUMERIC,
                        coef NUMERIC,
                        status TEXT DEFAULT 'pending'
                    );
                ''')
                
            logger.info("Все таблицы базы данных успешно проверены и обновлены.")
        except Exception as e:
            logger.critical(f"Ошибка при инициализации базы данных: {e}", exc_info=True)
            raise e

db = Database()
