"""Non-executing Deye charging dry-run: explain decisions and retain audit history.

This file deliberately imports no Home Assistant service helpers and exposes
no write-capable adapter. 'Proponowana komenda' is always hypothetical.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")

MAX_RECORDS = 1000
KEEP_DAYS = 8
PERIOD_MINUTES = 15
STALE_PLAN_SECONDS = 35 * 60


def _utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _view_now(now: datetime) -> str:
    at = _utc(now)
    if at is None:
        raise ValueError("Dry-run requires timezone-aware timestamp")
    return at.isoformat()


def evaluate_dry_run(
    *, now: datetime, plan: dict | None, grid: dict | None, tou: dict | None,
    soc: float | None, ev_kw: float | None, tariff_band: str | None,
    plan_computed_at: str | None, bms_confirmed: bool = False,
) -> dict:
    """Observe one possible adjustment without issuing any Deye commands.

    The physical grid guard and confirmed per-phase currents must be validated
    before any real automation. A plan remains hypothetical even when its
    measured grid headroom and TOU read-back appear complete.
    """
    at = _utc(now)
    timestamp = _view_now(now)
    p, g, t = plan or {}, grid or {}, tou or {}
    target = _number(p.get("target_soc"))
    nominal_power = _number(p.get("power_kw"))
    allowed_power = _number(g.get("allowed_charge_kw"))
    current_import = _number(g.get("import_kw"))
    charge_now = _number(g.get("current_charge_kw"))
    current_soc = _number(soc)
    observed_ev = _number(ev_kw)
    output = {
        "at": timestamp,
        "status": "blokada",
        "code": "NOT_READY",
        "why": "Brak kompletnego, aktualnego planu",
        "plan_status": p.get("status", "brak"),
        "plan_start": p.get("start"),
        "plan_end": p.get("end_window"),
        "target_soc_pct": target,
        "soc_now_pct": current_soc,
        "requested_kw": nominal_power,
        "suggested_kw": None,
        "grid_allowed_kw": allowed_power,
        "grid_import_kw": current_import,
        "battery_charge_now_kw": charge_now,
        "ev_kw": observed_ev,
        "tariff_band": tariff_band,
        "grid_state": g.get("state"),
        "phase_checked": bool(g.get("phase_checked")),
        "tou_status": t.get("status"),
        "blockers": [],
        "commands_sent": 0,
        "control_enabled": False,
        "readback_confirmed": False,
    }
    blockers = output["blockers"]
    computed = _utc(plan_computed_at)
    if computed is None or not 0 <= (at - computed).total_seconds() <= STALE_PLAN_SECONDS:
        blockers.append("Plan nie był ostatnio przeliczany lub jest starszy niż 35 minut")
    if p.get("status") != "wstepny_plan" or not isinstance(p.get("start"), str):
        blockers.append("Nie ma wykonalnej propozycji ładowania (15-minutowy planista)")
    if target is None or not 0 <= target <= 100 or current_soc is None or not 0 <= current_soc <= 100:
        blockers.append("Brak poprawnego SOC lub docelowego SOC")
    if nominal_power is None or not 0 < nominal_power <= 100:
        blockers.append("Brak poprawnej proponowanej mocy ładowania")
    if allowed_power is None or g.get("state") == "blokada":
        blockers.append("Grid Guard nie potwierdził bezpiecznego zapasu mocy")
    if not g.get("phase_checked", False):
        blockers.append("Brak wiarygodnego pomiaru i limitów L1/L2/L3")
    if t.get("status") != "odczytano_6_programow":
        blockers.append("Niezweryfikowana mapa sześciu programów Deye TOU")
    if not bms_confirmed:
        blockers.append("Brak zweryfikowanego limitu ładowania BMS i reakcji falownika")
    if tariff_band is None:
        blockers.append("Nie znam aktualnej strefy taryfowej")

    start = _utc(p.get("start"))
    finish = _utc(p.get("end_window"))
    if start is None or finish is None or finish <= start:
        blockers.append("Brak poprawnego przedziału ładowania")
    # Describe what the scheduler *would* want to do, separately from
    # whether hardware safety permits execution. This is useful even when
    # phases, BMS and the Deye write interface are still unverified.
    hypothetical = None
    if start is not None and finish is not None and nominal_power is not None:
        if current_soc is not None and target is not None and current_soc >= target - .1:
            hypothetical = "cel_osiagniety"
            output["suggested_kw"] = 0.
        elif at < start:
            hypothetical = "czekaj"
            output["suggested_kw"] = 0.
        elif at >= finish:
            hypothetical = "okno_zakonczone"
            output["suggested_kw"] = 0.
        elif tariff_band != "cheap":
            hypothetical = "poza_tania_taryfa"
            output["suggested_kw"] = 0.
        elif allowed_power is None:
            hypothetical = "brak_danych_o_mocy"
        elif allowed_power <= 0:
            hypothetical = "wstrzymaj_ladowanie"
            output["suggested_kw"] = 0.
        else:
            hypothetical = "laduj_z_ograniczeniem" if allowed_power < nominal_power else "laduj_planowo"
            output["suggested_kw"] = round(max(0., min(nominal_power, allowed_power)), 2)
    output["hipotetyczna_akcja"] = hypothetical
    if blockers:
        output["code"] = "SAFETY_BLOCKERS"
        output["why"] = "; ".join(blockers[:3])
        return output

    if current_soc >= target - 0.1:
        output.update(status="cel_osiagniety", code="TARGET_MET",
                      why="SOC osiągnął cel; w symulacji nie potrzeba ładowania",
                      suggested_kw=0.)
    elif at < start:
        output.update(status="oczekiwanie", code="WAITING_FOR_WINDOW",
                      why="Planowane tanie okno jeszcze się nie zaczęło",
                      suggested_kw=0.)
    elif at >= finish:
        output.update(status="po_oknie", code="WINDOW_ENDED",
                      why="Zakończyło się okno planowanego ładowania",
                      suggested_kw=0.)
    elif tariff_band != "cheap":
        output.update(status="poza_taryfa", code="EXPENSIVE_ZONE",
                      why="Nie jesteśmy w taniej strefie; brak ładowania z sieci",
                      suggested_kw=0.)
    else:
        recommendation = min(nominal_power, allowed_power)
        output.update(
            status="symulacja", code="SIMULATED_SETPOINT",
            why=("Hipotetyczna nastawa po ograniczeniu do zapasu mocy; "
                 "nie wysłano żadnej komendy do Deye"),
            suggested_kw=round(max(0., recommendation), 2),
        )
    return output


class DryRunJournal:
    """Persist 8 days of compact 15-minute snapshots and relevant transitions."""

    def __init__(self, saved: Any = None):
        stored = saved if isinstance(saved, dict) else {}
        self.records = list(stored.get("records", []))[-MAX_RECORDS:]
        self.latest = stored.get("latest") if isinstance(stored.get("latest"), dict) else None
        self.samples = max(0, int(stored.get("samples", len(self.records))))
        self.last_record_at = stored.get("last_record_at")
        self.last_code = stored.get("last_code")

    def observe(self, event: dict, *, force: bool = False) -> bool:
        """Return true only when new disk-persistable entry was added."""
        timestamp = _utc(event.get("at"))
        if timestamp is None:
            raise ValueError("Invalid dry-run event timestamp")
        previous = _utc(self.last_record_at)
        change = (
            event.get("code") != self.last_code
            or self.latest is None
            or event.get("suggested_kw") != self.latest.get("suggested_kw")
            or event.get("plan_start") != self.latest.get("plan_start")
            or event.get("target_soc_pct") != self.latest.get("target_soc_pct")
            or event.get("grid_state") != self.latest.get("grid_state")
            or event.get("hipotetyczna_akcja") != self.latest.get("hipotetyczna_akcja")
            or event.get("why") != self.latest.get("why")
        )
        self.latest = dict(event)
        if not force and not change and previous is not None and (
            timestamp - previous
        ).total_seconds() < PERIOD_MINUTES * 60:
            return False
        if previous is not None and timestamp < previous:
            # HA clock reset: don't invent historical decisions.
            return False
        record = {
            "at": event["at"], "status": event.get("status"), "code": event.get("code"),
            "why": str(event.get("why", ""))[:260],
            "suggested_kw": event.get("suggested_kw"),
            "hipotetyczna_akcja": event.get("hipotetyczna_akcja"),
            "requested_kw": event.get("requested_kw"),
            "target_soc_pct": event.get("target_soc_pct"),
            "soc_now_pct": event.get("soc_now_pct"),
            "grid_import_kw": event.get("grid_import_kw"),
            "grid_allowed_kw": event.get("grid_allowed_kw"),
            "ev_kw": event.get("ev_kw"),
            "phase_checked": event.get("phase_checked") is True,
            "commands_sent": 0,
        }
        cutoff = timestamp - timedelta(days=KEEP_DAYS)
        self.records = [
            old for old in self.records
            if _utc(old.get("at")) is not None and _utc(old["at"]) >= cutoff
        ]
        self.records.append(record)
        self.records = self.records[-MAX_RECORDS:]
        self.last_record_at = event["at"]
        self.last_code = event.get("code")
        self.samples += 1
        return True

    def report(self) -> dict:
        slots: dict[str, set[int]] = {}
        for event in self.records:
            at = _utc(event.get("at"))
            if at is None:
                continue
            local = at.astimezone(WARSAW)
            key = local.date().isoformat()
            # Multiple state transitions in one quarter are ONE sample,
            # never evidence of an entire day of uninterrupted observation.
            quarter = int(at.timestamp()) // (PERIOD_MINUTES * 60)
            slots.setdefault(key, set()).add(quarter)
        # A complete 24-hour day usually has 96 quarters; DST may yield
        # 92 or 100. Require >=80 separate slots, not event count.
        full_days = sum(len(points) >= 80 for points in slots.values())
        return {
            "status": (self.latest or {}).get("status", "brak_pomiarow"),
            "ostatnia_decyzja": self.latest,
            "ostatnia_proba": self.last_record_at,
            "zapisanych_decyzji": len(self.records),
            "lacznie_zapisanych": self.samples,
            "pelnych_dni_testu": full_days,
            "wymagane_dni_testu": 7,
            "dni_do_testu": max(0, 7 - full_days),
            "ostatnie_zdarzenia": list(reversed(self.records[-20:])),
            "gotowosc_sterowania": False,
            "komendy_wyslane": 0,
        }

    def export(self) -> dict:
        return {
            "records": self.records,
            "latest": self.latest,
            "samples": self.samples,
            "last_record_at": self.last_record_at,
            "last_code": self.last_code,
        }
