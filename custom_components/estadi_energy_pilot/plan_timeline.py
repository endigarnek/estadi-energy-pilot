"""Honest, bounded hour-by-hour battery schedule preview (never commands Deye).

Reads scenario_economics output for two simulations using identical inputs:
baseline PV/discharge and the hypothetical approved cheap-grid charge plan.
No future battery charging is presented as physically executed.
"""
from __future__ import annotations

from math import isfinite


def _numeric(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _rounded(value):
    number = _numeric(value)
    return round(number, 2) if number is not None else None


def build_plan_timeline(economics: dict | None) -> dict:
    """Small dashboard payload: 48 rows at most, explicit gaps and source."""
    result = {
        "status": "brak_danych", "reason": "Brak scenariuszy 48h",
        "hours": 0, "planned_hours": 0, "timeline": [],
        "charge_from_grid_kwh": None, "battery_to_home_kwh": None,
        "planned_grid_import_kwh": None, "baseline_grid_import_kwh": None,
        "forecast_not_execution": True, "deye_commands_sent": 0,
    }
    if not isinstance(economics, dict):
        return result
    baseline = economics.get("baseline") or {}
    projected = economics.get("plan") or {}
    base_rows = baseline.get("timeline_hours") or []
    plan_rows = projected.get("timeline_hours") or []
    if not isinstance(base_rows, list):
        return result

    have_plan = bool(projected and isinstance(plan_rows, list) and plan_rows)
    rows = []
    mismatched = False
    for index, base in enumerate(base_rows[:48]):
        if not isinstance(base, dict):
            break
        second = plan_rows[index] if have_plan and index < len(plan_rows) else None
        if second is not None and (
            not isinstance(second, dict) or second.get("czas") != base.get("czas")
        ):
            mismatched = True
            break
        charged = _numeric(second.get("grid_battery_kwh")) if second else None
        pv_to_batt = _numeric(second.get("pv_battery_kwh")) if second else None
        discharged = _numeric(second.get("battery_to_load_kwh")) if second else None
        # One row is one hour in scenario_economics, not instantaneous W.
        if charged is not None and charged > 0.01:
            mode = "ladowanie_z_sieci"
        elif pv_to_batt is not None and pv_to_batt > 0.01:
            mode = "ladowanie_z_pv"
        elif discharged is not None and discharged > 0.01:
            mode = "rozladowanie"
        elif second:
            mode = "spoczynek"
        else:
            mode = "brak_planu"
        rows.append({
            "czas": str(base.get("czas") or ""),
            "soc_bazowy_pct": _rounded(base.get("soc_end")),
            "soc_plan_pct": _rounded(second.get("soc_end")) if second else None,
            "pv_kwh": _rounded(base.get("pv_kwh")),
            "dom_kwh": _rounded(base.get("home_kwh")),
            "import_bazowy_kwh": _rounded(base.get("import_kwh")),
            "import_plan_kwh": _rounded(second.get("import_kwh")) if second else None,
            "ladowanie_siec_kwh": _rounded(charged),
            "ladowanie_pv_kwh": _rounded(pv_to_batt),
            "rozladowanie_kwh": _rounded(discharged),
            "moc_ladowania_siec_kw_sr": _rounded(charged),
            "tryb": mode,
        })
    if mismatched:
        # Never connect an hourly forecast to the wrong hour.
        result.update(status="blad_wyrownania", reason="Niezgodne osie czasu scenariuszy")
        return result
    n_plan = min(len(plan_rows), 48) if have_plan else 0
    status = ("gotowy" if have_plan and n_plan == 48 and
              len(rows) == 48 and baseline.get("status") == "gotowy"
              and projected.get("status") == "gotowy" else
              "niepelna_prognoza" if
              (baseline.get("status") != "gotowy" or
               projected.get("status") not in ("gotowy", None)) else
              "brak_planu")
    result.update({
        "status": status,
        "reason": (economics.get("reason") or "Brak kompletnego planu"),
        "hours": len(rows),
        "planned_hours": n_plan,
        "timeline": rows,
    })
    if status == "gotowy":
        result.update(
            charge_from_grid_kwh=_rounded(projected.get("grid_battery_kwh")),
            battery_to_home_kwh=_rounded(projected.get("battery_to_load_kwh")),
            planned_grid_import_kwh=_rounded(projected.get("import_kwh")),
            baseline_grid_import_kwh=_rounded(baseline.get("import_kwh")),
        )
    return result
