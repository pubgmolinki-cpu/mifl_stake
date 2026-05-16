import asyncpg
import logging
from config import DATABASE_URL

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Установка соединения с базой данных (создание пула)"""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(DATABASE_URL)
                logger.info("🎉 Успешное подключение к базе данных PostgreSQL!")
                await self.create_tables()
            except Exception as e:
                logger.error(f"❌ Ошибка подключения к БД: {e}")
                raise e

    async def create_tables(self):
        """Создание структуры таблиц, если они не существуют"""
        async with self.pool.acquire() as conn:
            # Таблица пользователей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    balance REAL DEFAULT 1000.0,
                    referrer_id BIGINT DEFAULT NULL
                );
            ''')

            # Таблица матчей (исправленная версия)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS matches (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    coef_p1 REAL, 
                    coef_x REAL, 
                    coef_p2 REAL,
                    coef_tb REAL, 
                    coef_tm REAL,
                    coef_oz_yes REAL, 
                    coef_oz_no REAL,
                    status TEXT DEFAULT 'active'
                );
            ''')

            # Таблица ставок (поддерживает и одинары, и экспрессы через массивы)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bets (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    match_ids INT[] NOT NULL,
                    outcomes TEXT[] NOT NULL,
                    bet_type TEXT NOT NULL, -- 'single' или 'express'
                    amount REAL NOT NULL,
                    coef REAL NOT NULL,
                    status TEXT DEFAULT 'pending', -- 'pending', 'won', 'lost'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')
            logger.info("🗄️ Все таблицы базы данных проверены/созданы.")

    # --- РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ---

    async def get_user(self, user_id: int):
        """Получить данные пользователя. Если его нет в базе — автоматически создать"""
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not user:
                await conn.execute(
                    "INSERT INTO users (user_id, balance) VALUES ($1, 1000.0)", 
                    user_id
                )
                user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            return user

    async def register_user_with_referrer(self, user_id: int, username: str, referrer_id: int):
        """Регистрация нового пользователя по реферальной ссылке"""
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not user:
                # Создаем пользователя с бонусом (например, 250 звезд другу)
                await conn.execute(
                    "INSERT INTO users (user_id, username, balance, referrer_id) VALUES ($1, $2, 1250.0, $3)",
                    user_id, username, referrer_id
                )
                # Начисляем бонус тому, кто пригласил (500 звезд)
                await conn.execute(
                    "UPDATE users SET balance = balance + 500.0 WHERE user_id = $1",
                    referrer_id
                )
                return True
            return False

    async def update_balance(self, user_id: int, amount: float):
        """Изменение баланса (может принимать как положительные, так и отрицательные числа)"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2", 
                float(amount), user_id
            )

    async def get_referrals_count(self, user_id: int) -> int:
        """Получить количество приглашенных пользователей"""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id = $1", user_id)
            return count or 0

    # --- РАБОТА С МАТЧАМИ ---

    async def get_active_matches(self):
        """Получить список всех доступных для ставок матчей"""
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM matches WHERE status = 'active' ORDER BY id DESC")

    # --- РАБОТА СО СТАВКАМИ И СТАТИСТИКОЙ ---

    async def add_bet(self, user_id: int, match_ids: list, outcomes: list, bet_type: str, amount: float, coef: float):
        """Сохранить новую ставку в базу данных"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                '''INSERT INTO bets (user_id, match_ids, outcomes, bet_type, amount, coef) 
                   VALUES ($1, $2, $3, $4, $5, $6)''',
                user_id, match_ids, outcomes, bet_type, float(amount), float(coef)
            )

    async def get_user_stats(self, user_id: int) -> dict:
        """Вычисление детальной статистики ставок для профиля"""
        async with self.pool.acquire() as conn:
            # Получаем все завершенные ставки пользователя
            bets = await conn.fetch("SELECT status, amount, coef FROM bets WHERE user_id = $1", user_id)
            
            total = len(bets)
            wins = sum(1 for b in bets if b['status'] == 'won')
            losses = sum(1 for b in bets if b['status'] == 'lost')
            
            # Считаем чистый профит
            profit = 0.0
            for b in bets:
                if b['status'] == 'won':
                    profit += (b['amount'] * b['coef']) - b['amount']
                elif b['status'] == 'lost':
                    profit -= b['amount']

            winrate = (wins / total * 100) if total > 0 else 0.0
            
            # Вычисляем позицию в топе по балансу
            top_position = await conn.fetchval(
                '''SELECT position FROM (
                    SELECT user_id, ROW_NUMBER() OVER (ORDER BY balance DESC) as position FROM users
                   ) as sub WHERE user_id = $1''', user_id
            )

            return {
                "total": total,
                "wins": wins,
                "losses": losses,
                "profit": round(profit, 2),
                "winrate": round(winrate, 1),
                "top_position": top_position or "—"
            }

    async def get_top_users(self, limit: int = 10):
        """Получить список лучших игроков по балансу для таблицы лидеров"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT username, user_id, balance FROM users ORDER BY balance DESC LIMIT $1", 
                limit
            )

    async def close(self):
        """Закрытие пула соединений при остановке бота"""
        if self.pool:
            await self.pool.close()
            logger.info("🔒 Пул подключений к БД закрыт.")

# Экспортируем готовый объект базы данных для импорта в другие файлы
db = Database()
