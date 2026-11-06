"""Evidence-based comparison of SOC scenarios, plan targets and day-ahead PV.

Only *observations* from Home Assistant are compared against predictions fixed
BEFORE their target time. The current 48h simulation intentionally excludes
extra grid charging and future EV sessions, so its SOC deviation is NOT proof
that an automatic controller was right or wrong.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import isfinite
from typing import Any

HORIZONS_H = (3, 6, 12, 24)
SNAPSHOT_INTERVAL_H = 6
MAX_PENDING_LAG_MIN = 45
KEEP_DAYS = 14
MAX_CHECKPOINTS = 240


def parse_instant(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def valid_soc(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if isfinite(num) and 0 <= num <= 100 else None


def pv_verification(history_summaries: list[dict]) -> dict:
    """Score day-ahead PV snapshots only on complete past measurement days."""
    valid = []
    for day in history_summaries:
        if not day.get("comparable"):
            continue
        actual = day.get("pv_kwh")
        predicted = day.get("forecast_pv_kwh")
        if (isinstance(actual, (int, float)) and
            isinstance(predicted, (int, float)) and
            isfinite(actual) and isfinite(predicted) and
            actual >= 0 and predicted >= 0):
            valid.append((float(predicted), float(actual)))
    count = len(valid)
    if not valid:
        return {
            "dni": 0, "sredni_blad_bezwzgledny_kwh": None,
            "wape_pct": None, "bias_kwh": None, "status": "brak_danych",
        }
    errors = [pred - actual for pred, actual in valid]
    actual_sum = sum(actual for _, actual in valid)
    return {
        "dni": count,
        "sredni_blad_bezwzgledny_kwh": round(sum(map(abs, errors)) / count, 2),
        "wape_pct": round(100 * sum(map(abs, errors)) / actual_sum, 1)
        if actual_sum > .1 else None,
        "bias_kwh": round(sum(errors) / count, 2),
        "status": "wiarygodniejsza" if count >= 7 else "zbieranie_danych",
        "uwaga": "Tylko dni z kompletnym pomiarem PV i prognoza zamrozona poprzedniego wieczoru",
    }


class AccuracyJournal:
    """Small persistent forecast archive; restarts cannot rewrite old forecasts."""

    def __init__(self, data: Any = None):
        saved = data if isinstance(data, dict) else {}
        self.checkpoints = list(saved.get("checkpoints", []))[-MAX_CHECKPOINTS:]
        self.last_issue_at = saved.get("last_issue_at")
        self.last_plan_end = saved.get("last_plan_end")

    def _cleanup(self, now: datetime) -> None:
        cutoff = now - timedelta(days=KEEP_DAYS)
        self.checkpoints = [
            entry for entry in self.checkpoints
            if (ts := parse_instant(entry.get("issued_at"))) is not None and ts >= cutoff
        ][-MAX_CHECKPOINTS:]

    def capture(self, now: datetime, simulation: dict | None,
                plan: dict | None, *, nominal_kwh: float | None = None) -> bool:
        """Freeze next 3/6/12/24h forecasts, at most once every 6 hours.

        Each scenario snapshot is *immutable* and is not a historical actual
        or a command to charge. A plan's target is saved separately, once for
        the corresponding end-of-cheap-window instant.
        """
        utc = parse_instant(now)
        if utc is None:
            raise ValueError("Timezone required")
        changed = False
        sim = simulation or {}
        previous = parse_instant(self.last_issue_at)
        if (sim.get("status") == "gotowa" and
                (previous is None or utc - previous >= timedelta(hours=SNAPSHOT_INTERVAL_H))):
            hourly = sim.get("timeline_hours", [])
            if isinstance(hourly, list) and len(hourly) >= max(HORIZONS_H):
                for horizon in HORIZONS_H:
                    row = hourly[horizon - 1]
                    predicted = valid_soc(row.get("soc_do")) if isinstance(row, dict) else None
                    if predicted is None:
                        continue
                    self.checkpoints.append({
                        "kind": "soc_without_grid_charge",
                        "issued_at": utc.isoformat(),
                        "due_at": (utc + timedelta(hours=horizon)).isoformat(),
                        "horizon_h": horizon,
                        "predicted_soc_pct": predicted,
                        "observed_soc_pct": None,
                        "status": "pending",
                        "scenario_quality": sim.get("quality"),
                        "nominal_kwh": nominal_kwh,
                    })
                    changed = True
                if changed:
                    self.last_issue_at = utc.isoformat()
        scheduled = plan or {}
        due = parse_instant(scheduled.get("end_window"))
        target = valid_soc(scheduled.get("target_soc"))
        if (scheduled.get("status") == "wstepny_plan" and due is not None and
                target is not None and utc < due <= utc + timedelta(hours=48) and
                self.last_plan_end != due.isoformat()):
            self.checkpoints.append({
                "kind": "recommended_target_observation",
                "issued_at": utc.isoformat(),
                "due_at": due.isoformat(),
                "horizon_h": None,
                "predicted_soc_pct": target,
                "observed_soc_pct": None,
                "status": "pending",
                "scenario_quality": "doradczy_bez_wykonania",
                "nominal_kwh": nominal_kwh,
                "proposed_power_kw": scheduled.get("power_kw"),
                "plan_start": scheduled.get("start"),
            })
            self.last_plan_end = due.isoformat()
            changed = True
        self._cleanup(utc)
        return changed

    def observe(self, now: datetime, measured_soc: float | None) -> bool:
        """Resolve due checkpoints only when a fresh, measured SOC exists.

        A missed observation stays 'brak_odczytu', never a zero or success.
        """
        utc = parse_instant(now)
        if utc is None:
            raise ValueError("Timezone required")
        actual = valid_soc(measured_soc)
        changed = False
        for entry in self.checkpoints:
            if entry.get("status") != "pending":
                continue
            due = parse_instant(entry.get("due_at"))
            if due is None:
                entry["status"] = "blad_daty"
                changed = True
                continue
            if utc < due:
                continue
            lag = utc - due
            if lag > timedelta(minutes=MAX_PENDING_LAG_MIN):
                entry["status"] = "brak_odczytu"
                changed = True
            elif actual is not None:
                predicted = valid_soc(entry.get("predicted_soc_pct"))
                if predicted is None:
                    entry["status"] = "bledna_prognoza"
                else:
                    entry["observed_soc_pct"] = round(actual, 1)
                    entry["observed_at"] = utc.isoformat()
                    entry["deviation_pp"] = round(actual - predicted, 1)
                    entry["status"] = (
                        "zaobserwowano" if entry.get("kind") == "soc_without_grid_charge"
                        else "cel_osiagniety" if actual >= predicted - .1
                        else "cel_nieosiagniety"
                    )
                changed = True
        self._cleanup(utc)
        return changed

    def report(self, history_summaries: list[dict] | None = None) -> dict:
        by_horizon = {}
        for horizon in HORIZONS_H:
            matched = [
                entry for entry in self.checkpoints
                if entry.get("kind") == "soc_without_grid_charge"
                and entry.get("horizon_h") == horizon
                and entry.get("status") == "zaobserwowano"
                and isinstance(entry.get("deviation_pp"), (int, float))
            ]
            absolute = [abs(entry["deviation_pp"]) for entry in matched]
            by_horizon[str(horizon)] = {
                "porownania": len(matched),
                "mae_soc_pp": round(sum(absolute) / len(absolute), 1) if absolute else None,
                "srednie_odchylenie_pp": round(
                    sum(entry["deviation_pp"] for entry in matched) / len(matched), 1
                ) if matched else None,
                "status": "wstepne" if len(matched) < 7 else "porownywalne",
            }
        observations = [
            entry for entry in self.checkpoints
            if entry.get("kind") == "recommended_target_observation"
            and entry.get("status") in ("cel_osiagniety", "cel_nieosiagniety")
        ]
        outcomes = {key: sum(row["status"] == key for row in observations)
                    for key in ("cel_osiagniety", "cel_nieosiagniety")}
        missing = sum(row.get("status") == "brak_odczytu" for row in self.checkpoints)
        pending = sum(row.get("status") == "pending" for row in self.checkpoints)
        return {
            "stan": "zbieranie_danych" if not observations and
            all(x["porownania"] < 7 for x in by_horizon.values()) else "porownania_dostepne",
            "horyzonty_soc": by_horizon,
            "obserwacje_celu": outcomes,
            "obserwacje_razem": len(observations),
            "brak_odczytu_w_terminie": missing,
            "oczekujace": pending,
            "liczba_migawek": len(self.checkpoints),
            "ostatnia_migawka": self.last_issue_at,
            "pv": pv_verification(history_summaries or []),
            "ostatnie_12": list(reversed(self.checkpoints[-12:])),
            "automatyzacja_wlaczona": False,
            "oszczednosci_pln": None,
            "uwaga": (
                "Odchylenia SOC dotyczą symulacji BEZ dodatkowego ładowania z sieci i "
                "BEZ przyszłych sesji EV. Wynik pokazuje różnicę scenariusza od realnego "
                "SOC, nie trafność automatycznych decyzji. Obserwacja osiągnięcia celu "
                "nie oznacza, że system wykonał ładowanie. Kosztów oszczędności nie "
                "podajemy bez potwierdzonych przepływów i cen eksportu."
            ),
        }

    def export(self) -> dict:
        return {
            "checkpoints": self.checkpoints,
            "last_issue_at": self.last_issue_at,
            "last_plan_end": self.last_plan_end,
        }
