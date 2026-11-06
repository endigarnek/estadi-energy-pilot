"""Offline, non-leaky review of Deye Load, EV and PV forecast history.

Training excludes the evaluated day; EV and heat pump are subtracted exactly
once from Deye Load. Incomplete observations are never assumed to be zero.
Everything here is informational: suggested calibration is not applied to Deye.
"""
from __future__ import annotations

from datetime import date
from math import ceil, isfinite
from statistics import median
from typing import Any

MAX_DAYS = 30
MIN_COVERAGE_H = .9
MIN_DAY_HOURS = 22
MIN_TRAIN_DAYS = 3
MIN_EV_DAYS = 7
MIN_TEST_HOURS = 72


def _number(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (float, int)) or not isfinite(x) or x < 0:
        return None
    return float(x)


def _channel(record: dict, key: str, hour: str) -> float | None:
    energy = _number(record.get("actual", {}).get(key, {}).get(hour))
    coverage = _number(record.get("coverage", {}).get(key, {}).get(hour))
    if energy is None or coverage is None or coverage < MIN_COVERAGE_H:
        return None
    # No silently assuming a device stopped if source coverage was absent.
    return energy


def _base_row(record: dict) -> list[float | None]:
    result = []
    for h in range(24):
        name = f"{h:02}:00"
        home = _channel(record, "home", name)
        ev = _channel(record, "ev", name)
        pump = _channel(record, "heat_pump", name)
        if (home is None or ev is None or pump is None
                or ev > home + .2 or pump > home - ev + .2):
            result.append(None)
            continue
        result.append(max(0., home - ev - pump))
    return result


def _ev_row(record: dict) -> list[float | None]:
    return [_channel(record, "ev", f"{h:02}:00") for h in range(24)]


def _history(history_days: dict, today: date) -> list[tuple[date, dict]]:
    rows = []
    for marker, record in history_days.items():
        try:
            day = date.fromisoformat(marker)
        except (ValueError, TypeError):
            continue
        if not isinstance(record, dict) or not 0 < (today - day).days <= MAX_DAYS:
            continue
        rows.append((day, record))
    return sorted(rows)


def _p90(values: list[float]) -> float:
    values = sorted(values)
    return values[max(0, min(len(values) - 1, ceil(.9 * len(values)) - 1))]


def analyze_load_history(history_days: dict, today: date) -> dict:
    """Hold out each historical day's measurements before fitting hour p50.

    A day-type sample (weekday/weekend) must exist BEFORE each evaluated day;
    this is not same-day fitting and the metrics are not from invented data.
    """
    dated = _history(history_days, today)
    complete = [(day, _base_row(record)) for day, record in dated]
    complete = [(day, hours) for day, hours in complete
                if sum(value is not None for value in hours) >= MIN_DAY_HOURS]
    errors = []
    expected_sum = observed_sum = 0.
    evaluated_days = set()
    for pos, (day, hours) in enumerate(complete):
        peers = [past for prior, past in complete[:pos]
                 if (prior.weekday() >= 5) == (day.weekday() >= 5)]
        if len(peers) < MIN_TRAIN_DAYS:
            continue
        scored = 0
        for hour, actual in enumerate(hours):
            samples = [past[hour] for past in peers if past[hour] is not None]
            if actual is None or len(samples) < MIN_TRAIN_DAYS:
                continue
            predicted = median(samples)
            errors.append(actual - predicted)
            expected_sum += predicted
            observed_sum += actual
            scored += 1
        if scored >= MIN_DAY_HOURS:
            evaluated_days.add(day.isoformat())
    valid = len(errors) >= MIN_TEST_HOURS and len(evaluated_days) >= 3
    all_valid = [number for _, hours in complete for number in hours
                 if number is not None]
    base_p50 = median(all_valid) if all_valid else None
    return {
        "status": "oceniono" if valid else "zbieranie_danych",
        "complete_days": len(complete),
        "evaluated_days": len(evaluated_days),
        "tested_hours": len(errors),
        "mae_kwh_hour": round(sum(abs(e) for e in errors) / len(errors), 3) if errors else None,
        "wape_pct": round(100 * sum(abs(e) for e in errors) / observed_sum, 1)
        if observed_sum > .1 else None,
        "bias_actual_minus_forecast_kwh_hour": round(sum(errors) / len(errors), 3)
        if errors else None,
        "base_median_w": round(1000 * base_p50) if base_p50 is not None else None,
        "recommendation": (
            "Profil domu jest testowany na kolejnych dniach, bez użycia danych z dnia testowego."
            if valid else
            "Wymagane co najmniej 3 historyczne dni tego samego typu przed każdym testem, "
            "co najmniej 3 dni testowe i 72 poprawne godziny."
        ),
        "auto_calibration_enabled": False,
        "home_includes_ev_and_heat_pump": True,
    }


def analyze_ev_history(history_days: dict, today: date) -> dict:
    """Upper-stress hourly EV profile from complete observed days.

    Per-hour P90 is a collection of separate historical percentiles, NOT a
    90% joint-probability guarantee for any 48-hour journey or charging session.
    """
    dated = _history(history_days, today)
    complete = [(day, _ev_row(record)) for day, record in dated]
    complete = [(day, hours) for day, hours in complete
                if sum(value is not None for value in hours) >= MIN_DAY_HOURS]
    kinds = {}
    for kind in ("weekday", "weekend"):
        matching = [hours for day, hours in complete
                    if (day.weekday() >= 5) == (kind == "weekend")]
        hour_rows = []
        for hour in range(24):
            observed = [row[hour] for row in matching if row[hour] is not None]
            if len(observed) < MIN_TRAIN_DAYS:
                hour_rows.append(None)
                continue
            hour_rows.append(round(_p90(observed), 3))
        kinds[kind] = {
            "sample_days": len(matching),
            "p90_kwh_per_hour": hour_rows,
            "peak_hour_kwh": max((h for h in hour_rows if h is not None), default=None),
            "hours_with_risk": sum(h is not None and h > 0.1 for h in hour_rows),
        }
    ready = len(complete) >= MIN_EV_DAYS and all(
        group["sample_days"] >= MIN_TRAIN_DAYS for group in kinds.values()
    )
    return {
        "status": "gotowy_scenariusz_stresowy" if ready else "za_malo_danych",
        "complete_days": len(complete),
        "required_complete_days": MIN_EV_DAYS,
        "profiles": kinds if ready else {},
        "risk_ready": ready,
        "future_sessions_known": False,
        "model_type": "historyczny_P90_godzinowy_scenariusz_stresowy",
        "warning": (
            "Wartości P90 z wielu godzin mogą reprezentować różne historyczne sesje; "
            "połączony profil NIE jest prognozą prawdopodobieństwa ani znanym "
            "harmonogramem EV. Pierwszy kwadrans nadal korzysta z bieżącego pomiaru."
        ),
    }


def pv_bias_guidance(summaries: list[dict]) -> dict:
    """Suggest conservative PV derate based on locked day-ahead forecast.

    No automatic application. Ignore incomplete days and near-zero forecasts.
    """
    eligible = []
    for row in summaries:
        if not row.get("comparable"):
            continue
        p, a = _number(row.get("forecast_pv_kwh")), _number(row.get("pv_kwh"))
        if p is None or a is None or p < .5:
            continue
        eligible.append((p, a))
    forecast = sum(p for p, _ in eligible)
    actual = sum(a for _, a in eligible)
    factor = actual / forecast if forecast else None
    ready = len(eligible) >= 7
    discount = round(max(0, min(40, (1 - factor) * 100))) if factor is not None and ready else None
    return {
        "status": "rekomendacja" if ready else "zbieranie_danych",
        "complete_pv_days": len(eligible),
        "historical_actual_forecast_ratio": round(factor, 3) if factor is not None else None,
        "suggested_total_pv_discount_pct": discount,
        "note": (
            "Jest to sugerowana CAŁKOWITA korekta prognozy, nie dodatkowa "
            "korekta nakładana na już ustawiony rabat PV. "
            "Nie stosujemy jej automatycznie; porównaj ją z własnym ustawieniem."
        ),
        "auto_apply": False,
    }
