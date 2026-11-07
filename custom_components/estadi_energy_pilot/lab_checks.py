"""ESTADI diagnostic lab — live read-only checks without Deye service calls.

Diagnostic buttons have zero write capability. Actual actuator experiments
require a separate, explicitly approved adapter with safety and rollback tests.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .const import (
    CONF_GRID_POWER, CONF_BATTERY_POWER, CONF_GRID_IMPORT_SIGN,
    CONF_BATTERY_CHARGE_SIGN, CONF_PHASE_LIMIT_L1,
    CONF_PHASE_LIMIT_L2, CONF_PHASE_LIMIT_L3,
)
from .grid_monitor import build_grid_readout, read_source
from .deye_tou import inspect_tou

DIAGNOSTIC_TESTS = {
    "meters": "Sprawdź odczyty sieci i baterii",
    "polarity": "Sprawdź kalibrację kierunków",
    "limits": "Sprawdź Grid Guard i fazy",
    "forecast": "Sprawdź prognozę i plan",
    "tou": "Sprawdź harmonogram Deye TOU",
    "write_capability": "Regulatory Deye — pierwsza strona (bez zapisu)",
    "write_capability_more": "Regulatory Deye — druga strona (bez zapisu)",
    "preflight": "Sprawdź kompletność warunków do sterowania (bez zapisu)",
}

def _result(kind: str, status: str, reason: str, **data) -> dict:
    return {"test":kind,"status":status,"reason":reason,
            "command_sent":False,"actual_power_change_verified":False,**data}


def inspect_test(kind: str, *, states, selected: dict, coordinator_data: dict,
                 now: datetime, same_deye_device_entities: set[str] | None = None) -> dict:
    """Return a structured and auditable result from actual HA states only."""
    if kind not in DIAGNOSTIC_TESTS:
        raise ValueError("Nieznany test ESTADI")
    if kind == "meters":
        grid=read_source(states.get,selected.get(CONF_GRID_POWER),now,"power")
        battery=read_source(states.get,selected.get(CONF_BATTERY_POWER),now,"power")
        valid=grid["status"]=="ok" and battery["status"]=="ok"
        return _result(kind,"ok" if valid else "blokada",
            "Odczytano źródła, ale kierunki mocy wymagają odrębnej kalibracji" if valid
            else "Co najmniej jeden czujnik jest nieaktualny, niedostępny lub źle skonfigurowany",
            grid_entity=grid["entity_id"],grid_status=grid["status"],
            grid_signed_kw=(round(grid["value"]/1000,3) if grid["value"] is not None else None),
            battery_entity=battery["entity_id"],battery_status=battery["status"],
            battery_signed_kw=(round(battery["value"]/1000,3) if battery["value"] is not None else None),
            grid_age_s=grid["age_s"],battery_age_s=battery["age_s"])
    if kind == "polarity":
        grid=selected.get(CONF_GRID_IMPORT_SIGN,0)
        batt=selected.get(CONF_BATTERY_CHARGE_SIGN,0)
        confirmed=grid in (-1,1) and batt in (-1,1)
        return _result(kind,"ok" if confirmed else "blokada",
            "Znaki wybrane w konfiguracji; wymagana nadal niezależna weryfikacja import/eksport i BMS" if confirmed
            else "Brak potwierdzenia kierunku sieci lub baterii — nie włączamy wykonania",
            grid_sign=grid,battery_charge_sign=batt,hardware_verified=False)
    if kind == "limits":
        g=build_grid_readout(states.get,selected,now)
        phase_limits=[selected.get(k) for k in (
            CONF_PHASE_LIMIT_L1,CONF_PHASE_LIMIT_L2,CONF_PHASE_LIMIT_L3)]
        return _result(kind,"ok" if g.get("state")=="ok" else "blokada",
            g.get("reason") or "Brak wyniku",
            grid_status=g.get("state"),measured_import_kw=g.get("import_kw"),
            headroom_kw=g.get("headroom_kw"),
            allowed_charge_kw=g.get("allowed_charge_kw"),
            phase_check=g.get("phase_status"),
            phase_limits_a=phase_limits,connection_limit_kw=g.get("connection_limit_kw"),
            hardware_verified=False)
    if kind == "forecast":
        energy=coordinator_data.get("energy_2_0") or {}
        sim=energy.get("simulation_48h") or {}
        coverage=energy.get("pv_coverage") or {}
        smart=energy.get("optimized_schedule") or {}
        complete=sim.get("status")=="gotowa" and float(sim.get("forecast_hours") or 0)>=47.75
        return _result(kind,"ok" if complete else "blokada",
            "Prognoza kompletna — plan doradczy nie jest wykonanym poleceniem" if complete
            else sim.get("reason") or "Niepełna godzinowa prognoza PV",
            hours=sim.get("forecast_hours"),simulation_status=sim.get("status"),
            source=coverage.get("source"),
            daylight_covered_pct=coverage.get("covered_daylight_pct"),
            missing_daylight_steps=coverage.get("missing_daylight_steps"),
            first_missing_daylight_at=coverage.get("first_missing_daylight_at"),
            source_candidates=coverage.get("candidate_sources"),
            plan_status=smart.get("status"),plan_reason=smart.get("reason"),
            start=smart.get("start"),power_kw=smart.get("power_kw"),
            battery_grid_charge_kwh=smart.get("grid_charge_kwh"))
    if kind == "tou":
        observed=inspect_tou(states.async_all(),now)
        return _result(kind,"ok" if observed.get("odczytane_pola")==24 else "blokada",
            observed.get("przyczyna") or "Brak odczytu",
            read_fields=observed.get("odczytane_pola"),missing_fields=observed.get("brakujace_pola"),
            slots=observed.get("programy"),readback_only=True,
            hardware_write_ready=False,blockers=observed.get("blokady",[]))
    if kind == "preflight":
        guard = build_grid_readout(states.get, selected, now)
        solar = (coordinator_data.get("energy_2_0") or {}).get("pv_coverage") or {}
        sim = (coordinator_data.get("energy_2_0") or {}).get("simulation_48h") or {}
        plan = (coordinator_data.get("energy_2_0") or {}).get("optimized_schedule") or {}
        problems = []
        if guard.get("state") != "ok":
            problems.append("Grid Guard: " + str(guard.get("reason") or guard.get("state")))
        if not guard.get("import_sign_confirmed"):
            problems.append("Znak importu sieci Deye niepotwierdzony")
        if not guard.get("charge_sign_confirmed"):
            problems.append("Znak ładowania baterii niepotwierdzony")
        if not guard.get("phase_checked"):
            problems.append("Niepotwierdzony pomiar i limity trzech faz")
        if not (sim.get("status") == "gotowa" and sim.get("forecast_hours") == 48):
            problems.append("Symulacja 48h niekompletna")
        if plan.get("status") != "wstepny_plan":
            problems.append("Brak wstępnego planu ładowania")
        # These missing physical verifications cannot be inferred from HA
        # states or from the mere existence of number/select controls.
        problems.extend([
            "Niepotwierdzony protokół zapisu i odczyt zwrotny Deye",
            "Brak pomiarowego testu zmiany mocy ładowania",
            "Brak zatwierdzonych ograniczeń BMS",
            "Brak procedury rollback po awarii lub zaniku komunikacji",
        ])
        return _result(
            kind, "blokada", "Sterowanie fizyczne pozostaje wyłączone",
            blockers=problems, blocker_count=len(problems),
            grid_guard=guard.get("state"),
            phase_status=guard.get("phase_status"),
            forecast_source=solar.get("source"),
            forecast_hours=sim.get("forecast_hours"),
            plan_status=plan.get("status"),
            write_test_approved=False, remote_control_enabled=False,
        )
    # Discover candidate controls on the SAME HA device as the configured
    # Deye meter. Some legitimate devices expose generic entity IDs without
    # "deye" in their slug. This is inventory only: no write capability proof.
    related = same_deye_device_entities or set()
    candidates = []
    checked = 0
    for entity in states.async_all():
        entity_id = getattr(entity, "entity_id", "")
        domain = entity_id.partition(".")[0]
        if domain not in ("number", "select", "switch"):
            continue
        attrs = getattr(entity, "attributes", {}) or {}
        name = str(attrs.get("friendly_name") or entity_id)
        text = (entity_id + " " + name).lower()
        from_device = entity_id in related
        if not from_device and not any(token in text for token in (
            "deye", "time_of_use", "time of use", "tou_",
        )):
            continue
        if not any(token in text for token in (
            "charge", "charging", "battery", "power", "program",
            "time_of_use", "time of use", "tou", "soc", "export",
            "grid", "work mode",
        )):
            continue
        checked += 1
        options = attrs.get("options")
        if not isinstance(options, (list, tuple)):
            options = []
        candidates.append({
            "entity": entity_id,
            "label": name[:100],
            "domain": domain,
            "state": str(getattr(entity, "state", "unknown"))[:70],
            "unit": attrs.get("unit_of_measurement"),
            "min": attrs.get("min"),
            "max": attrs.get("max"),
            "step": attrs.get("step"),
            "options": [str(v)[:60] for v in options[:20]],
            "detected_by": "same_deye_device" if from_device else "name_match",
            "command_written": False,
            "readback_verified": False,
            "safe_limits_verified": False,
        })
    # Physical risk before naming: charging toggles/TOU and current limits
    # must not be buried behind battery voltage, chemistry or grid-code setup.
    # Stable across both pages, max 40 candidates/HA sensor state to avoid
    # oversized Home Assistant Recorder state attributes.
    def priority(item: dict) -> tuple[int, int, str]:
        name = item["entity"].lower()
        if any(word in name for word in (
            "grid_charging", "grid_charge", "time_of_use", "use_timer",
            "program_grid", "program_charge", "tou_grid", "tou_charge",
        )):
            level = 0
        elif any(word in name for word in (
            "battery_max_charging_current", "grid_max_import_power",
            "grid_peak_shaving", "battery_max_discharging_current",
        )):
            level = 1
        elif "program_" in name or "_tou_" in name:
            level = 2
        elif "work_mode" in name or "battery_capacity" in name:
            level = 3
        else:
            level = 4
        return (level, item["detected_by"] != "same_deye_device", name)

    candidates.sort(key=priority)
    page = 1 if kind == "write_capability" else 2
    per_page = 40
    pages = (checked + per_page - 1) // per_page
    start_at = (page - 1) * per_page
    selected_candidates = candidates[start_at:start_at + per_page]
    return _result(
        kind, "blokada",
        "Wykryto regulatory, ale nie potwierdzono fizycznego zapisu ani reakcji Deye.",
        candidates=selected_candidates, discovered=checked,
        page=page, pages=pages, first_index=start_at + 1,
        shown=len(selected_candidates),
        remaining=max(0, checked-start_at-len(selected_candidates)),
        truncated=checked > page*per_page,
        same_deye_device_count=sum(x["detected_by"] == "same_deye_device"
                                   for x in candidates),
        scanned_from="Rejestr urządzeń HA + Stany (tylko odczyt)",
        actual_write_test_available=False,
        next_step="Wyślij wykaz z obu stron, zwłaszcza przełączniki i "
                  "programy TOU. Bez zatwierdzenia parametrów nie uruchamiamy zapisu.",
    )
