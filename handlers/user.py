from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

router = Router()

# 1. Определяем состояния (если у тебя они называются иначе, используй свои)
class BetStates(StatesGroup):
    waiting_for_amount = State()

# 2. Хэндлер нажатия на инлайн-кнопку исхода (например, П1, Х, П2 и т.д.)
# Вставьте или измените свой хэндлер, который обрабатывает клик по коэффициенту:
@router.callback_query(F.data.startswith("bet_")) # Предположим, callback_data кнопок выглядит как "bet_p1", "bet_tb2.5"
async def select_bet_outcome(callback: CallbackQuery, state: FSMContext):
    # Вытаскиваем сам исход из callback_data (например: 'p1')
    chosen_outcome = callback.data.split("_")[1]
    
    # СУПЕР ВАЖНО: Записываем тип ставки в FSM, чтобы он не улетел в БД как null
    await state.update_data(bet_type=chosen_outcome)
    
    # Отправляем сообщение и переводим юзера в состояние ожидания ввода суммы
    await callback.message.answer(
        f"📊 Вы выбрали исход: {chosen_outcome.upper()}.\n"
        "💰 Введите сумму ставки в чат:"
    )
    await state.set_state(BetStates.waiting_for_amount)
    await callback.answer()

# 3. Исправленный хэндлер ввода суммы (Примерно строка 183 в твоем файле)
@router.message(BetStates.waiting_for_amount)
async def accept_bet_amount(message: Message, state: FSMContext):
    # Проверяем, что введено число
    if not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите сумму ставки цифрами (целое число).")
        return

    bet_amount = int(message.text)
    
    # Вытаскиваем данные, которые мы сохранили на шаге клика по кнопке
    data = await state.get_data()
    bet_type = data.get('bet_type') # Тот самый bet_type, который вызывал ошибку NotNullViolationError
    
    # Защитная проверка: если стейт почему-то пуст, не пускаем запрос к БД, чтобы не было ошибки
    if not bet_type:
        await message.answer("❌ Произошла ошибка: потерян выбранный исход. Начните оформление ставки заново через меню 'Матчи'.")
        await state.clear()
        return

    user_id = message.from_user.id

    try:
        # --- Твой блок работы с Базой Данных (asyncpg / psycopg) ---
        # Убедись, что переменная bet_type передается в SQL-запрос INSERT на нужное место.
        # Примерный вид твоего запроса:
        # await conn.execute(
        #     "INSERT INTO bets (user_id, bet_type, amount, status) VALUES ($1, $2, $3, $4)",
        #     user_id, bet_type, bet_amount, 'pending'
        # )
        
        # ЕСЛИ ВСЁ ПРОШЛО УСПЕШНО:
        await message.answer(f"✅ Ставка успешно принята!\nИсход: {bet_type.upper()}\nСумма: {bet_amount}")
        await state.clear() # Очищаем стейт после успешной ставки

    except Exception as e:
        # Вывод ошибки в консоль Render, чтобы ты её видел
        print(f"Ошибка при сохранении ставки: {e}") 
        await message.answer("❌ Произошла ошибка на сервере при оформлении ставки. Попробуйте еще раз.")
