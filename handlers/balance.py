from aiogram import Router, types, F
from database import get_user_banks

router = Router()

@router.callback_query(F.data == "menu:balance")
async def show_balance(callback: types.CallbackQuery):
    try:
        rows = await get_user_banks(callback.from_user.id)
    except RuntimeError:
        await callback.message.edit_text("❌ Ошибка: база данных не подключена")
        await callback.answer()
        return

    if not rows:
        await callback.message.edit_text("У тебя пока нет данных по банкам")
    else:
        text = "📊 Баланс:\n" + "\n".join(
            [f"{r['bank_name']}: {r['balance']:.2f}₸" for r in rows]
        )
        await callback.message.edit_text(text)

    await callback.answer()
