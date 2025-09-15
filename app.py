import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from database import init_db, close_db
from handlers import routers  # список роутеров

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

async def main():
    # Инициализация БД
    await init_db()
    logging.info("✅ Database initialized")

    # Подключаем все роутеры
    for r in routers:
        dp.include_router(r)
        logging.info(f"✅ Router {r} included")

    try:
        logging.info("✅ Bot started polling")
        await dp.start_polling(bot)
    finally:
        # Закрываем пул соединений при остановке
        await close_db()
        logging.info("✅ Database closed")

if __name__ == "__main__":
    asyncio.run(main())
