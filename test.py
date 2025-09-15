import asyncio
import logging
import os
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from config import *


logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ---------Categories-----------
categories  = ["Food", "Bus", "Taxi", "Entertainment", "Other"]

def get_category_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=cat, callback_data=f"cat:{cat}")] for cat in categories
        ]
    )

# --- FSM states ---
class ExpenseForm(StatesGroup):
    waiting_for_amount = State()
    waiting_for_custom_name = State()
    waiting_for_custom_amount = State()

# ---DB pool(global) ---
db_pool: asyncpg.Pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(
        user = DB_USER,
        password = DB_PASS,
        database = DB_NAME,
        host = DB_HOST
    )
    async with db_pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            category VARCHAR(50),
            amount NUMERIC(10,2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

# --- Start command ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Выбери категорию расхода:",
        reply_markup=get_category_keyboard()
    )

# --- Category pressed ---
@dp.callback_query(lambda c: c.data and c.data.startswith("cat:"))
async def handle_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("cat:")[1]
    await callback.message.edit_reply_markup(reply_markup=None)

    if category == "Other":
        await state.set_state(ExpenseForm.waiting_for_custom_name)
        await state.update_data(category=category)
        await callback.message.answer("На что именно потратил?")
    else:
        await state.set_state(ExpenseForm.waiting_for_amount)
        await state.update_data(category=category)
        await callback.message.answer(f"Ты выбрал категорию: {category}\nВведи сумму:")

    await callback.answer()

# --- Custom name for "Другое" ---
@dp.message(ExpenseForm.waiting_for_custom_name)
async def process_custom_name(message: types.Message, state: FSMContext):
    await state.update_data(custom_name=message.text)
    await state.set_state(ExpenseForm.waiting_for_custom_amount)
    await message.answer("Теперь введи сумму")

# --- Amount for all categories ---
@dp.message(ExpenseForm.waiting_for_amount)
@dp.message(ExpenseForm.waiting_for_custom_amount)
async def process_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи число")
        return

    amount = int(message.text)
    data = await state.get_data()

    category = data.get("category")
    if category == "Other":
        custom_name = data.get("custom_name")
        category_text = f"Other: {custom_name}"
    else:
        category_text = category

    # Save to database
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO expenses (user_id, category, amount) VALUES ($1, $2, $3)",
            message.from_user.id, category_text, amount
            )
    await message.answer(f"Записано: {amount} тенге на категорию '{category_text}' ✅")
    await state.clear()

# --- Run ---
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
