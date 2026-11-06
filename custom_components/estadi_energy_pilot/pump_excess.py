"""Explain unusual electrical heat-pump load, without guessing a cause.

Evaluates ONLY finished historical days, using temperature-band reference
values trained on STRICTLY OLDER days. A pump-power anomaly is not proof
of DHW, defrost, immersion heater, compressor short-cycling or a fault.
Hourly integral data cannot distinguish those causes.
No HA state mutations, notifications or inverter service calls.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .heat_pump_learning import (
    _fit, _hourly_pairs, MIN_BIN_DAYS,
)

# Demand at least 0.65 extra kWh over the historical P50 per valid hour,
# and 135% of the historical P90. Never flag tiny standby readings.
MIN_EXTRA_KWH = 0.65
P90_MULTIPLIER = 1.35
MIN_ACTUAL_KWH = 1.0
MIN_SCORE_HOURS = 24
MIN_SCORE_DAYS = 3
MAX_RECENT_EVENTS = 20


def _merge_anomalies(day: date, hours: list[dict]) -> list[dict]:
    """Merge only consecutive, validated anomalous hours on the same date."""
    events = []
    current: list[dict] = []

    def finish() -> None:
        if not current:
            return
        start_hour = current[0]["hour"]
        last = current[-1]["hour"] + 1
        events.append({
            "start": f"{day.isoformat()}T{start_hour:02d}:00:00",
            "end": (f"{day.isoformat()}T{last:02d}:00:00"
                    if last < 24 else
                    f"{(day + timedelta(days=1)).isoformat()}T00:00:00"),
            "hours": len(current),
            "actual_kwh": round(sum(x["actual_kwh"] for x in current), 2),
            "expected_p50_kwh": round(sum(x["p50_kwh"] for x in current), 2),
            "estimated_excess_kwh": round(
                sum(max(0, x["actual_kwh"] - x["p50_kwh"]) for x in current), 2
            ),
            "min_outdoor_temp_c": min(x["temp_lower"] for x in current),
            "max_outdoor_temp_c": max(x["temp_upper"] for x in current),
            "possible_causes_not_verified": True,
            "cause": "nieustalona",
        })

    for hour in hours:
        if current and hour["hour"] != current[-1]["hour"] + 1:
            finish()
            current = []
        current.append(hour)
    if current:
        finish()
    return events


def inspect_pump_excess(days: dict[str, Any], today: date) -> dict:
    """Chronological detection of sustained high electrical draw.

    - Only actual paired temperature + energy with >=90% coverage per hour.
    - Build a P50/P90 band from *previous dates only*.
    - Undertrained/missing ranges are unknown, not a normal hour nor an event.
    - All data refers to completed days; no live or past-forecast claims.
    """
    dates = _hourly_pairs(days, today)
    prior = []
    observed_hours = 0
    scored_hours = 0
    eligible_days = set()
    excess_hours = 0
    total_extra = 0.0
    events = []
    for day, rows in dates:
        trained = _fit(prior)
        anomalous = []
        scored_day = 0
        for h, entry in enumerate(rows):
            if entry is None:
                continue
            observed_hours += 1
            band_idx, actual = entry
            base = trained.get(str(band_idx))
            if base is None:
                continue
            p50 = float(base["srednia_moc_p50_w"]) / 1000
            p90 = float(base["srednia_moc_p90_w"]) / 1000
            scored_hours += 1
            scored_day += 1
            # Rely on both an absolute and relative threshold. This is
            # a conservative excess-energy flag, not a cycle diagnosis.
            if (actual >= MIN_ACTUAL_KWH and
                    actual >= p50 + MIN_EXTRA_KWH and
                    actual >= p90 * P90_MULTIPLIER):
                excess_hours += 1
                total_extra += max(0, actual - p50)
                anomalous.append({
                    "hour": h,
                    "actual_kwh": actual,
                    "p50_kwh": p50,
                    "temp_lower": base["temperatura_min_c"],
                    "temp_upper": base["temperatura_max_c"],
                })
        if scored_day >= 6:
            eligible_days.add(day)
        events.extend(_merge_anomalies(day, anomalous))
        # Fit is intentionally updated only AFTER scoring the whole day.
        # Keep incomplete hours out of the reference model.
        prior.extend((day, bucket, energy)
                     for pair in rows if pair is not None
                     for bucket, energy in [pair])
    ready = scored_hours >= MIN_SCORE_HOURS and len(eligible_days) >= MIN_SCORE_DAYS
    return {
        "status": "oceniono_odchylenia" if ready else "zbieranie_danych",
        "historical_days_seen": len(dates),
        "minimum_days_before_band": MIN_BIN_DAYS,
        "hours_with_temperature_and_energy": observed_hours,
        "hours_compared_with_older_days": scored_hours,
        "days_evaluated": len(eligible_days),
        "suspected_high_load_hours": excess_hours,
        "estimated_excess_energy_kwh": round(total_extra, 2)
        if ready else None,
        "event_count": len(events) if ready else None,
        "last_event_start": events[-1]["start"] if ready and events else None,
        "latest_events": events[-MAX_RECENT_EVENTS:] if ready else [],
        "min_excess_kwh_per_hour": MIN_EXTRA_KWH,
        "p90_multiplier": P90_MULTIPLIER,
        "automatic_actions": False,
        "confirmed_dhw_cycles": None,
        "confirmed_defrost_cycles": None,
        "confirmed_faults": None,
        "interpretation": (
            "Wykryto wyłącznie ponadnormatywne elektryczne zużycie pompy "
            "w godzinach ze znaną temperaturą. Bez temperatury obiegu/CWU, "
            "stanu sprężarki i sygnału defrost NIE można ustalić, czy przyczyną "
            "była CWU, odszranianie, grzałka, inny tryb czy usterka. "
            "Pomiar godzinowy nie pozwala policzyć cykli sprężarki. "
            "Zdarzenia pochodzą tylko z zakończonych dni; "
            "brak historii to brak oceny, a nie brak anomalii."
        ),
    }
