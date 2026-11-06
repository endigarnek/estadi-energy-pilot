"""Evidence-based heat-pump electric power by measured outdoor temperature.

Historical data is paired only when BOTH actual pump kWh and outside degrees C
have 90%+ hourly coverage. Training never includes today. Forward-holdout
compares each day's observation with older days only (no hindsight leakage).
Model is advisory: it NEVER replaces the default planner automatically.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import ceil, isfinite
from statistics import median
from typing import Any

from .engine import TempSlot, pump_power_w
from .simulation_48h import _temperature

EDGES = (-45, -10, -5, 0, 5, 10, 15, 25, 55)
MIN_HOUR_COVERAGE = .9
MIN_DAYS = 7
MIN_BIN_HOURS = 6
MIN_BIN_DAYS = 3
MIN_TRAIN_BINS = 2
MAX_DAYS = 30
MIN_VALID_HOURS = 48
MIN_EVALUATED_HOURS = 12
MAX_HOURLY_ENERGY = 15.
STEP_H = .25


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (ValueError, TypeError):
        return None
    return n if isfinite(n) else None


def _hourly_pairs(days: dict, today: date) -> list[tuple[date, list[tuple[int, float] | None]]]:
    """Complete day/hour pairs; local DST repeated hour is rejected if >1h."""
    output = []
    for key, record in days.items():
        try:
            day = date.fromisoformat(key)
        except (ValueError, TypeError):
            continue
        if not 0 < (today - day).days <= MAX_DAYS or not isinstance(record, dict):
            continue
        actual = record.get("actual") or {}
        coverage = record.get("coverage") or {}
        temp_sum = record.get("temperature_degree_hours") or {}
        temp_cover = record.get("temperature_coverage") or {}
        pump_actual = actual.get("heat_pump") or {}
        pump_cover = coverage.get("heat_pump") or {}
        rows = []
        for hour in range(24):
            marker = f"{hour:02}:00"
            energy = _num(pump_actual.get(marker))
            ecover = _num(pump_cover.get(marker))
            degree_hours = _num(temp_sum.get(marker))
            tcover = _num(temp_cover.get(marker))
            if (None in (energy, ecover, degree_hours, tcover)
                    or not MIN_HOUR_COVERAGE <= ecover <= 1.02
                    or not MIN_HOUR_COVERAGE <= tcover <= 1.02
                    or energy < 0 or energy > MAX_HOURLY_ENERGY):
                rows.append(None)
                continue
            temp = degree_hours / tcover
            bucket = _bin_for(temp)
            rows.append((bucket, energy) if bucket is not None else None)
        output.append((day, rows))
    return sorted(output)


def _bin_for(temp: float) -> int | None:
    if not isfinite(temp):
        return None
    for idx in range(len(EDGES) - 1):
        if EDGES[idx] <= temp < EDGES[idx + 1]:
            return idx
    return len(EDGES) - 2 if temp == EDGES[-1] else None


def _fit(observations: list[tuple[date, int, float]]) -> dict:
    bins: dict[str, dict] = {}
    for idx in range(len(EDGES) - 1):
        matches = [(day, kwh) for day, bucket, kwh in observations if bucket == idx]
        distinct = len({day for day, _ in matches})
        if len(matches) < MIN_BIN_HOURS or distinct < MIN_BIN_DAYS:
            continue
        values = sorted(kwh for _, kwh in matches)
        p90 = values[max(0, min(len(values) - 1, ceil(.9 * len(values)) - 1))]
        bins[str(idx)] = {
            "temperatura_min_c": EDGES[idx],
            "temperatura_max_c": EDGES[idx + 1],
            "srednia_moc_p50_w": round(median(values) * 1000),
            "srednia_moc_p90_w": round(p90 * 1000),
            "godziny": len(matches),
            "rozne_dni": distinct,
        }
    return bins


def train_heat_pump(days: dict, today: date, *,
                    mild_w: float = 600, cold_w: float = 1200) -> dict:
    """Build supported temperature bands and strictly forward test past days."""
    history = _hourly_pairs(days, today)
    complete = [(day, rows) for day, rows in history
                if sum(row is not None for row in rows) >= 20]
    observations: list[tuple[date, int, float]] = []
    errors = []
    tested_days = set()
    for day, rows in history:
        # Evaluate ONLY on older observations; do not include today's row.
        past_bins = _fit(observations)
        predicted_count = 0
        for pair in rows:
            if pair is None:
                continue
            bucket, actual_kwh = pair
            prediction = past_bins.get(str(bucket))
            if prediction is None:
                continue
            errors.append(actual_kwh - prediction["srednia_moc_p50_w"] / 1000)
            predicted_count += 1
        if predicted_count >= 3:
            tested_days.add(day)
        observations.extend((day, pair[0], pair[1]) for pair in rows if pair is not None)
    bands = _fit(observations)
    eligible_days = len(complete)
    ready = (eligible_days >= MIN_DAYS and len(observations) >= MIN_VALID_HOURS
             and len(bands) >= MIN_TRAIN_BINS)
    score_ready = len(errors) >= MIN_EVALUATED_HOURS and len(tested_days) >= 3
    total_abs = sum(abs(x) for x in errors)
    return {
        "status": "gotowy_podglad" if ready else "zbieranie_temperatury_i_energii",
        "quality": "oceniony" if score_ready else "wstepny",
        "days_complete": eligible_days,
        "days_with_any_pairs": sum(any(row is not None for row in rows) for _, rows in history),
        "valid_hours": len(observations),
        "bands": bands,
        "learned_bands": len(bands),
        "requirements": {
            "days_complete": MIN_DAYS,
            "paired_hours": MIN_VALID_HOURS,
            "temperature_bands": MIN_TRAIN_BINS,
            "hours_per_band": MIN_BIN_HOURS,
            "days_per_band": MIN_BIN_DAYS,
            "holdout_hours": MIN_EVALUATED_HOURS,
        },
        "holdout_hours": len(errors),
        "holdout_days": len(tested_days),
        "mae_kwh_h": round(total_abs / len(errors), 3) if errors else None,
        "bias_actual_minus_model_kwh_h": round(sum(errors) / len(errors), 3) if errors else None,
        "automatic_use": False,
        "heat_pump_is_separate_from_base_house": True,
        "note": (
            "Prognoza opiera się na rzeczywistym poborze prądu pompy i lokalnym "
            "pomiarze temperatury. Może obejmować CWU, odszranianie i postoje "
            "sprężarki; nie wyznacza COP ani temperatury zasilania. "
            "Niedostępne zakresy temperatur wymagają kolejnych pomiarów. "
            "Model wyłącznie do podglądu, bez automatycznego sterowania."
        ),
    }


def predict_pump_w(model: dict, degrees_c: float, *,
                   variant: str = "p50") -> float | None:
    """Return actual trained band power only; never extrapolate silently."""
    if model.get("status") != "gotowy_podglad":
        return None
    bucket = _bin_for(degrees_c)
    band = (model.get("bands") or {}).get(str(bucket))
    if band is None:
        return None
    field = "srednia_moc_p90_w" if variant == "p90" else "srednia_moc_p50_w"
    return _num(band.get(field))


def preview_48h(now: datetime, temps: list[TempSlot], current_temp: float,
                model: dict, *, mild_w: float, cold_w: float) -> dict:
    """Compare learned bands with old linear model only where temp is forecast.

    Missing weather and unseen temperature ranges are unknown — not 0 W.
    This does not modify the charge planner, scenario economics or 48h chart.
    """
    if now.tzinfo is None:
        raise ValueError("Timestamp must have a timezone")
    if model.get("status") != "gotowy_podglad":
        return {
            "status": "za_malo_danych",
            "porownywalne_godziny": 0,
            "prognoza_nauczona_kwh": None,
            "prognoza_dotychczasowa_kwh": None,
            "model_wlaczone_do_planowania": False,
        }
    learned = old = 0.
    matched = 0
    for index in range(192):
        at = now.astimezone(timezone.utc) + timedelta(minutes=15 * index)
        degrees, known = _temperature(at, temps, current_temp)
        if not known:
            continue
        prediction = predict_pump_w(model, degrees)
        if prediction is None:
            continue
        learned += prediction * STEP_H / 1000
        old += pump_power_w(degrees, mild_w=mild_w, cold_w=cold_w) * STEP_H / 1000
        matched += 1
    return {
        "status": "porownanie_wstepne" if matched >= 144 else "czesciowa_prognoza",
        "porownywalne_godziny": round(matched * STEP_H, 2),
        "prognoza_nauczona_kwh": round(learned, 2) if matched else None,
        "prognoza_dotychczasowa_kwh": round(old, 2) if matched else None,
        "roznica_kwh": round(learned - old, 2) if matched else None,
        "model_wlaczone_do_planowania": False,
        "data_missing_is_not_zero": True,
        "note": "Porównujemy tylko te kwadranse, gdzie jest pogoda i wyuczony zakres temperatur.",
    }
