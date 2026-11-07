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
    "write_capability": "Sprawdź dostępność regulacji mocy (bez zapisu)",
}

def _result(kind: str, status: str, reason: str, **data) -> dict:
    return {"test":kind,"status":status,"reason":reason,
            "command_sent":False,"actual_power_change_verified":False,**data}


def inspect_test(kind: str, *, states, selected: dict, coordinator_data: dict,
                 now: datetime) -> dict:
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
    # Discover actual write-capable candidate entities, but NEVER execute them.
    candidates=[]
    for entity in states.async_all():
        entity_id=getattr(entity,"entity_id","")
        if entity_id.split(".",1)[0] not in ("number","select","switch"):
            continue
        if not ("deye" in entity_id or "time_of_use" in entity_id or "tou_" in entity_id):
            continue
        if not any(word in entity_id for word in ("charge","charging","power","program","time_of_use","tou")):
            continue
        candidates.append({
            "entity":entity_id,"state":str(getattr(entity,"state","unknown"))[:70],
            "unit":(getattr(entity,"attributes",{}) or {}).get("unit_of_measurement"),
        })
    return _result(kind,"blokada",
        "Wykrycie encji number/select/switch nie potwierdza semantyki, zapisu, odczytu zwrotnego ani reakcji BMS",
        candidates=sorted(candidates,key=lambda x:x["entity"])[:40],
        discovered=len(candidates),actual_write_test_available=False,
        next_step="Prześlij dokładne encje sterujące Deye i ich jednostki; test zapisu wymaga dodatkowej zgody, limitów i rollbacku")
