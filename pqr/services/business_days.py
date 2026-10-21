"""
Días hábiles en Colombia para el plazo de las PQR (D21): lunes a viernes sin
festivos. Los festivos se calculan con la Ley 51 de 1983 («ley Emiliani»),
que traslada varios al lunes siguiente, y con la Pascua para los móviles.
"""
from datetime import date, datetime, time, timedelta, timezone

COLOMBIA_TZ = timezone(timedelta(hours=-5))

# Fijos: no se trasladan
FIXED_HOLIDAYS = ((1, 1), (5, 1), (7, 20), (8, 7), (12, 8), (12, 25))
# Se trasladan al lunes siguiente si no caen en lunes
MOVABLE_HOLIDAYS = ((1, 6), (3, 19), (6, 29), (8, 15), (10, 12), (11, 1), (11, 11))
# Días desde el domingo de Pascua: Jueves y Viernes Santo (fijos) y
# Ascensión, Corpus Christi y Sagrado Corazón (ya trasladados a lunes)
EASTER_OFFSETS = (-3, -2, 43, 64, 71)


def easter_sunday(year):
    """Domingo de Pascua (algoritmo anónimo gregoriano)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _next_monday(day):
    return day + timedelta(days=(7 - day.weekday()) % 7)


def colombian_holidays(year):
    holidays = {date(year, month, day) for month, day in FIXED_HOLIDAYS}
    holidays |= {_next_monday(date(year, month, day)) for month, day in MOVABLE_HOLIDAYS}
    easter = easter_sunday(year)
    holidays |= {easter + timedelta(days=offset) for offset in EASTER_OFFSETS}
    return holidays


def is_business_day(day):
    return day.weekday() < 5 and day not in colombian_holidays(day.year)


def add_business_days(moment, days):
    """
    Suma días hábiles a un datetime con zona horaria, contados en hora de
    Colombia desde el día siguiente. Conserva la hora del día.
    """
    local = moment.astimezone(COLOMBIA_TZ)
    day = local.date()
    remaining = days
    while remaining > 0:
        day += timedelta(days=1)
        if is_business_day(day):
            remaining -= 1
    return datetime.combine(day, time(local.hour, local.minute, local.second, local.microsecond),
                            tzinfo=COLOMBIA_TZ).astimezone(moment.tzinfo)
