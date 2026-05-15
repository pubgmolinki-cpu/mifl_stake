from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from database import db
from config import ADMIN_IDS
from states import AdminStates

router = Router()

@router.message(F.text == "/admin")
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("🛠 Панель админа:\n/add_match — Добавить новый матч\n/close_match — Рассчитать матч")

@router.message(F.text == "/add_match")
async def start_add_match(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("Введите название команд (например, `Германия — Италия`):")
    await state.set_state(AdminStates.add_match_title)

@router.message(AdminStates.add_match_title)
async def process_match_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите 7 коэффициентов через пробел:\n`П1 Х П2 ТБ ТМ ОЗ_Да ОЗ_Нет` (Пример: `1.5 3.1 2.5 1.8 1.9 1.7 2.0`)")
    await state.set_state(AdminStates.add_match_coefs)

@router.message(AdminStates.add_match_coefs)
async def process_match_coefs(message: types.Message, state: FSMContext):
    try:
        coefs = list(map(float, message.text.split()))
        if len(coefs) != 7:
            raise ValueError
        data = await state.get_data()
        await db.add_match(data['title'], *coefs)
        await message.answer("✅ Матч успешно добавлен в систему!")
        await state.clear()
    except ValueError:
        await message.answer("Ошибка ввода. Введите ровно 7 числовых коэффициентов.")
