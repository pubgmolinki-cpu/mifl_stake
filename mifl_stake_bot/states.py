from aiogram.fsm.state import State, StatesGroup


class BetState(StatesGroup):

    waiting_for_amount = State()
