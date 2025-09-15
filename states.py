from aiogram.fsm.state import State, StatesGroup

class ExpenseForm(StatesGroup):
    waiting_for_bank = State()
    waiting_for_amount = State()
    waiting_for_custom_name = State()
    waiting_for_custom_amount = State()


class DepositForm(StatesGroup):
    waiting_for_bank = State()
    waiting_for_amount = State()