def calculate_odds(
    home_rating,
    away_rating,
    home_form,
    away_form
):

    home_strength = (
        home_rating * 0.7 +
        home_form * 0.3
    )

    away_strength = (
        away_rating * 0.7 +
        away_form * 0.3
    )

    total = home_strength + away_strength

    home_probability = home_strength / total
    away_probability = away_strength / total

    draw_probability = 0.22

    home_probability *= 0.78
    away_probability *= 0.78

    odds_home = round(1 / home_probability, 2)
    odds_draw = round(1 / draw_probability, 2)
    odds_away = round(1 / away_probability, 2)

    over25 = 1.85
    under25 = 1.95

    btts_yes = 1.75
    btts_no = 2.05

    return {
        "home": odds_home,
        "draw": odds_draw,
        "away": odds_away,

        "over25": over25,
        "under25": under25,

        "btts_yes": btts_yes,
        "btts_no": btts_no
    }
