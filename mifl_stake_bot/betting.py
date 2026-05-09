from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


def betting_keyboard(match_id):

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="П1",
                    callback_data=f"bet:{match_id}:П1"
                ),

                InlineKeyboardButton(
                    text="X",
                    callback_data=f"bet:{match_id}:X"
                ),

                InlineKeyboardButton(
                    text="П2",
                    callback_data=f"bet:{match_id}:П2"
                )
            ],

            [
                InlineKeyboardButton(
                    text="ТБ 2.5",
                    callback_data=f"bet:{match_id}:OVER"
                ),

                InlineKeyboardButton(
                    text="ТМ 2.5",
                    callback_data=f"bet:{match_id}:UNDER"
                )
            ],

            [
                InlineKeyboardButton(
                    text="ОЗ Да",
                    callback_data=f"bet:{match_id}:BTTS_YES"
                ),

                InlineKeyboardButton(
                    text="ОЗ Нет",
                    callback_data=f"bet:{match_id}:BTTS_NO"
                )
            ]
        ]
    )

    return keyboard
