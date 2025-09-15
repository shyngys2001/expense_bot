from aiogram import Router, types
from aiogram.filters import CommandStart
from keyboards import get_main_menu

router = Router()

@router.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer("Привет! 👋 Выбери действие:", reply_markup=get_main_menu())
