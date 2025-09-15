import asyncpg
from config import DB_USER, DB_PASS, DB_NAME, DB_HOST
from decimal import Decimal

# Глобальный пул соединений
db_pool: asyncpg.Pool | None = None

async def init_db():
    """
    Инициализация пула БД и создание таблиц
    """
    global db_pool
    db_pool = await asyncpg.create_pool(
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        host=DB_HOST,
        min_size=1,
        max_size=10
    )
    print("✅ Database connected")

    async with db_pool.acquire() as conn:
        # Таблица расходов
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            category VARCHAR(50),
            bank VARCHAR(50),
            amount NUMERIC(12,2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Таблица банков
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS banks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            bank_name VARCHAR(50),
            balance NUMERIC(12,2) DEFAULT 0,
            UNIQUE(user_id, bank_name)
        );
        """)

        # Таблица доходов / пополнений
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS incomes (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            bank VARCHAR(50),
            amount NUMERIC(12,2) NOT NULL,
            description VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

async def close_db():
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
        print("✅ Database closed")

# ------------------------------
# Функции для работы с БД
# ------------------------------

async def get_user_banks(user_id: int):
    if db_pool is None:
        raise RuntimeError("Database not initialized")
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT bank_name, balance FROM banks WHERE user_id=$1",
            user_id
        )

async def add_expense(user_id: int, category: str, bank: str, amount: Decimal):
    if db_pool is None:
        raise RuntimeError("Database not initialized")
    async with db_pool.acquire() as conn:
        # создаем запись банка если её нет
        await conn.execute("""
            INSERT INTO banks (user_id, bank_name, balance)
            VALUES ($1, $2, 0)
            ON CONFLICT (user_id, bank_name) DO NOTHING
        """, user_id, bank)
        # списываем деньги
        await conn.execute("""
            UPDATE banks SET balance = balance - $1
            WHERE user_id=$2 AND bank_name=$3
        """, amount, user_id, bank)
        # сохраняем расход
        await conn.execute("""
            INSERT INTO expenses (user_id, category, bank, amount)
            VALUES ($1, $2, $3, $4)
        """, user_id, category, bank, amount)
        # возвращаем текущий баланс
        return await conn.fetchval(
            "SELECT balance FROM banks WHERE user_id=$1 AND bank_name=$2",
            user_id, bank
        )

async def add_income(user_id: int, bank_name: str, amount: Decimal):
    """
    Добавляет сумму на баланс пользователя и создаёт запись в таблице incomes
    """
    if db_pool is None:
        raise RuntimeError("Database not initialized")

    async with db_pool.acquire() as conn:
        # создаем запись банка если её нет
        await conn.execute("""
            INSERT INTO banks (user_id, bank_name, balance)
            VALUES ($1, $2, 0)
            ON CONFLICT (user_id, bank_name) DO NOTHING
        """, user_id, bank_name)

        # добавляем деньги на баланс
        await conn.execute("""
            UPDATE banks SET balance = balance + $1
            WHERE user_id=$2 AND bank_name=$3
        """, amount, user_id, bank_name)

        # создаём запись в incomes
        await conn.execute("""
            INSERT INTO incomes (user_id, bank, amount)
            VALUES ($1, $2, $3)
        """, user_id, bank_name, amount)

        # возвращаем текущий баланс
        balance = await conn.fetchval("""
            SELECT balance FROM banks WHERE user_id=$1 AND bank_name=$2
        """, user_id, bank_name)

    return balance

