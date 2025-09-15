from aiogram import Router, F, types
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from states import ExpenseForm
from keyboards import get_category_keyboard, get_bank_keyboard
from database import add_expense

router = Router()

@router.callback_query(F.data == "menu:expense")
async def expense_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выбери категорию:", reply_markup=get_category_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("cat:"))
async def handle_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("cat:")[1]
    await state.update_data(category=category)
    await callback.message.edit_text("Выбери банк:", reply_markup=get_bank_keyboard())
    await state.set_state(ExpenseForm.waiting_for_bank)
    await callback.answer()

@router.callback_query(F.data.startswith("bank:"), ExpenseForm.waiting_for_bank)
async def handle_bank(callback: CallbackQuery, state: FSMContext):
    bank = callback.data.split("bank:")[1]
    await state.update_data(bank=bank)
    data = await state.get_data()

    if data["category"] == "Other":
        await state.set_state(ExpenseForm.waiting_for_custom_name)
        await callback.message.edit_text("На что именно потратил?")
    else:
        await state.set_state(ExpenseForm.waiting_for_amount)
        await callback.message.edit_text(f"Категория: {data['category']}, Банк: {bank}\nВведи сумму:")
    await callback.answer()

@router.message(ExpenseForm.waiting_for_custom_name)
async def process_custom_name(message: types.Message, state: FSMContext):
    await state.update_data(custom_name=message.text)
    await state.set_state(ExpenseForm.waiting_for_custom_amount)
    await message.answer("Теперь введи сумму")

@router.message(F.state.in_([ExpenseForm.waiting_for_amount, ExpenseForm.waiting_for_custom_amount]))
async def process_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введи число")

    data = await state.get_data()
    category = data.get("category")
    bank = data.get("bank")
    if category == "Other":
        category = f"Other: {data.get('custom_name')}"

    balance = await add_expense(message.from_user.id, category, bank, int(message.text))
    await message.answer(f"💸 Записано: {message.text}₸ ({category}, {bank})\nОстаток: {balance:.2f}₸")
    await state.clear()
