from aiogram.fsm.state import StatesGroup, State

class AdminStates(StatesGroup):
    add_match_title = State()
    add_match_coefs = State()
    close_match_select = State()
    close_match_result = State()

class BetStates(StatesGroup):
    single_bet_amount = State()
    express_select_matches = State()
    express_select_outcomes = State()
    express_bet_amount = State()
