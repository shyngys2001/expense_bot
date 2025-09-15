from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

categories = ["Food", "Bus", "Taxi", "Entertainment", "Other"]
banks = ["Kaspi", "Halyk", "Freedom"]

def get_category_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=cat, callback_data=f"cat:{cat}")] for cat in categories]
    )

def get_bank_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=bank, callback_data=f"bank:{bank}")] for bank in banks]
    )

def get_main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Расход", callback_data="menu:expense")],
            [InlineKeyboardButton(text="💰 Пополнение", callback_data="menu:deposit")],
            [InlineKeyboardButton(text="📊 Баланс", callback_data="menu:balance")],
        ]
    )