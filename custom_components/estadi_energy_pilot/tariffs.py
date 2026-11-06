"""TAURON G12w/G13 zone calendar; no fictional energy prices.

Timezone is always Europe/Warsaw. Holiday set covers nationwide statutory days,
including Christmas Eve (since 2025). User-defined prices remain unset until entered.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
TARIFFS = ("G12w", "G13")
ZONE_NAMES = {
    "cheap": "Tania",
    "peak": "Droga",
    "morning": "Szczyt przedpołudniowy",
    "evening": "Szczyt popołudniowy",
}


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian computus, valid for supported Gregorian years."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def poland_public_holidays(year: int) -> set[date]:
    easter = easter_sunday(year)
    fixed = ((1, 1), (1, 6), (5, 1), (5, 3), (8, 15),
             (11, 1), (11, 11), (12, 25), (12, 26))
    holidays = {date(year, m, d) for m, d in fixed}
    if year >= 2025:
        holidays.add(date(year, 12, 24))
    holidays |= {easter, easter + timedelta(days=1),
                 easter + timedelta(days=49), easter + timedelta(days=60)}
    return holidays


def is_day_off(day: date, extra_holidays: set[date] | None = None) -> bool:
    return (day.weekday() >= 5 or day in poland_public_holidays(day.year)
            or bool(extra_holidays and day in extra_holidays))


def tariff_zone(moment: datetime, tariff: str = "G12w",
                extra_holidays: set[date] | None = None) -> str:
    if moment.tzinfo is None:
        raise ValueError("Naive timestamp not supported")
    if tariff not in TARIFFS:
        raise ValueError("Unrecognized tariff — do not guess prices")
    local = moment.astimezone(WARSAW)
    if is_day_off(local.date(), extra_holidays):
        return "cheap"
    hour = local.hour + local.minute / 60 + local.second / 3600
    if tariff == "G12w":
        return "cheap" if hour < 6 or 13 <= hour < 15 or hour >= 22 else "peak"
    if 7 <= hour < 13:
        return "morning"
    is_summer = 4 <= local.month <= 9
    if (19 <= hour < 22) if is_summer else (16 <= hour < 21):
        return "evening"
    return "cheap"


def zone_prices(
    tariff: str,
    price_cheap: float | None,
    price_peak: float | None,
    price_evening: float | None = None,
) -> dict[str, float] | None:
    """Return None until all real variable import prices are provided."""
    needed = {"cheap": price_cheap, "peak": price_peak}
    if tariff == "G13":
        needed["evening"] = price_evening
        needed["morning"] = price_peak
    elif tariff != "G12w":
        return None
    try:
        if any(v is None or not 0 < float(v) < 20 for v in needed.values()):
            return None
        return {key: float(value) for key, value in needed.items()}
    except (ValueError, TypeError):
        return None


def next_cheap_window(moment: datetime, tariff: str, *, horizon_days: int = 8) -> tuple[datetime, datetime] | None:
    """Find the continuous next cheap window. Preserve DST via UTC stepping."""
    if moment.tzinfo is None:
        raise ValueError("Naive timestamp not supported")
    # Step over absolute time; local date/time automatically handles DST folds.
    from datetime import timezone
    cursor = moment.astimezone(timezone.utc)
    cursor += timedelta(minutes=(15 - (cursor.minute % 15)) % 15,
                        seconds=-cursor.second, microseconds=-cursor.microsecond)
    began = None
    for index in range(horizon_days * 24 * 4):
        point = cursor + timedelta(minutes=15 * index)
        cheap = tariff_zone(point, tariff) == "cheap"
        if began is None and cheap:
            began = point
        elif began is not None and not cheap:
            return began.astimezone(WARSAW), point.astimezone(WARSAW)
    return None
