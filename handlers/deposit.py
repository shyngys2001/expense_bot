from aiogram import Router, F, types
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from states import DepositForm
from keyboards import get_bank_keyboard
from database import add_income

router = Router()

# --- меню → пополнение ---
@router.callback_query(F.data == "menu:deposit")
async def deposit_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выбери банк для пополнения:", reply_markup=get_bank_keyboard())
    await state.set_state(DepositForm.waiting_for_bank)
    await callback.answer()

# --- выбор банка ---
@router.callback_query(F.data.startswith("bank:"), DepositForm.waiting_for_bank)
async def deposit_bank(callback: CallbackQuery, state: FSMContext):
    bank_name = callback.data.split("bank:")[1]
    await state.update_data(bank=bank_name)
    await state.set_state(DepositForm.waiting_for_amount)
    await callback.message.edit_text(f"Банк: {bank_name}\nВведи сумму пополнения:")
    await callback.answer()

# --- ввод суммы ---
@router.message(F.state == DepositForm.waiting_for_amount)
async def deposit_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введи число")

    data = await state.get_data()
    bank_name = data["bank"]
    amount = int(message.text)

    # Добавляем доход и получаем текущий баланс
    balance = await add_income(message.from_user.id, bank_name, amount)

    await message.answer(f"✅ Пополнено {amount}₸ на {bank_name}\nБаланс: {balance:.2f}₸")
    await state.clear()
