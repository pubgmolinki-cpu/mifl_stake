def generate_analysis(
    home_team,
    away_team,
    home_rating,
    away_rating,
    home_form,
    away_form
):

    text = f"""
🤖 AI Анализ матча

⚔️ {home_team} vs {away_team}

"""

    if home_rating > away_rating:
        text += f"📈 {home_team} имеет более сильный состав.\n"
    else:
        text += f"📈 {away_team} имеет более сильный состав.\n"

    if home_form > away_form:
        text += f"🔥 {home_team} находится в лучшей форме.\n"
    else:
        text += f"🔥 {away_team} показывает лучшую форму.\n"

    difference = abs(home_rating - away_rating)

    if difference < 5:
        text += "\n⚖️ Матч выглядит очень равным."

    elif difference < 15:
        text += "\n👀 Есть небольшой фаворит."

    else:
        text += "\n🚨 Ожидается доминирование одной команды."

    return text
