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

    total_strength = home_strength + away_strength

    home_probability = home_strength / total_strength
    away_probability = away_strength / total_strength

    draw_probability = 0.22

    home_probability *= 0.78
    away_probability *= 0.78

    odds_home = round(1 / home_probability, 2)
    odds_draw = round(1 / draw_probability, 2)
    odds_away = round(1 / away_probability, 2)

    return {
        "home": odds_home,
        "draw": odds_draw,
        "away": odds_away
    }
