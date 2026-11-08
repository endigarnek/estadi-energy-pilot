"""Actionable, read-only preflight explanation for ESTADI Deye.

Separates operating configuration, missing telemetry and commissioning
conditions. Never considers current Grid Charge OFF a fault or asks a user
to enable it without the physical safety procedure.
"""
from __future__ import annotations

from math import isfinite

from .const import (
    CONF_BATTERY_POWER, CONF_GRID_POWER, CONF_BATTERY_CHARGE_SIGN,
    CONF_GRID_IMPORT_SIGN, CONF_GRID_LIMIT, CONF_PHASE_CURRENT_L1,
    CONF_PHASE_CURRENT_L2, CONF_PHASE_CURRENT_L3, CONF_PHASE_VOLTAGE_L1,
    CONF_PHASE_VOLTAGE_L2, CONF_PHASE_VOLTAGE_L3, CONF_PHASE_LIMIT_L1,
    CONF_PHASE_LIMIT_L2, CONF_PHASE_LIMIT_L3,
)


def _number(value):
    try:
        if isinstance(value, bool):
            return None
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if isfinite(number) else None


def build_preflight_steps(*, guard: dict, inventory: dict, selected: dict,
                          sim: dict, plan: dict, inverter_limit_w=None,
                          peak_shaving_state: str | None = None) -> dict:
    """Five concise stages, with explicit read/execute capability separation."""
    groups = []
    statuses = guard.get("source_status") or {}
    raw_grid = statuses.get(CONF_GRID_POWER) or {}
    raw_battery = statuses.get(CONF_BATTERY_POWER) or {}
    raw_battery_value = _number(guard.get("raw_battery_kw"))
    raw_grid_value = _number(guard.get("raw_grid_kw"))

    readings = []
    if raw_grid.get("stan") != "ok":
        readings.append("Odczyt mocy sieci jest nieaktualny lub niedostępny.")
    if raw_battery.get("stan") != "ok":
        readings.append("Odczyt mocy baterii jest nieaktualny lub niedostępny.")
    if selected.get(CONF_GRID_IMPORT_SIGN, 0) not in (-1, 1):
        readings.append("Nie wybrano kierunku importu sieci.")
    if selected.get(CONF_BATTERY_CHARGE_SIGN, 0) not in (-1, 1):
        readings.append("Nie wybrano kierunku ładowania baterii.")
    if not readings:
        readings.append(
            "Źródła i ustawienia kierunków są dostępne; potwierdzenie znaku "
            "wymaga porównania z rzeczywistą pracą falownika."
        )
    groups.append({
        "key": "meters", "title": "1. Odczyty i kierunki",
        "status": "wymaga" if any((
            raw_grid.get("stan") != "ok",
            raw_battery.get("stan") != "ok",
            selected.get(CONF_GRID_IMPORT_SIGN, 0) not in (-1, 1),
            selected.get(CONF_BATTERY_CHARGE_SIGN, 0) not in (-1, 1),
        )) else "ustawiono",
        "items": readings,
        "evidence": {
            "grid_entity": raw_grid.get("encja"), "grid_kw_raw": raw_grid_value,
            "battery_entity": raw_battery.get("encja"),
            "battery_kw_raw": raw_battery_value,
            "battery_charge_sign": selected.get(CONF_BATTERY_CHARGE_SIGN, 0),
            "grid_import_sign": selected.get(CONF_GRID_IMPORT_SIGN, 0),
        },
        "next_test": "Kierunki mocy",
    })

    phase_sources = (
        CONF_PHASE_CURRENT_L1, CONF_PHASE_CURRENT_L2, CONF_PHASE_CURRENT_L3,
        CONF_PHASE_VOLTAGE_L1, CONF_PHASE_VOLTAGE_L2, CONF_PHASE_VOLTAGE_L3,
    )
    unavailable = [
        name for name in phase_sources
        if (statuses.get(name) or {}).get("stan") != "ok"
    ]
    phase_ok = bool(guard.get("phase_checked"))
    connection_kw = _number(selected.get(CONF_GRID_LIMIT))
    phases = []
    if unavailable:
        phases.append("Brak aktualnych odczytów L1/L2/L3 prądu lub napięcia.")
    if not phase_ok:
        phases.append("Brak pełnej weryfikacji trzech faz i limitów prądowych.")
    if phase_ok:
        phases.append("Pomiary i ustawione limity faz są dostępne; zabezpieczenia fizyczne wymagają osobnej weryfikacji.")
    groups.append({
        "key": "phases", "title": "2. Fazy i przyłącze",
        "status": "ustawiono" if phase_ok else "wymaga",
        "items": phases,
        "evidence": {
            "connection_limit_kw": connection_kw,
            "phase_status": guard.get("phase_status"),
            "phase_source_status": {
                key: (statuses.get(key) or {}).get("stan") for key in phase_sources
            },
            "phase_limits_a": [
                selected.get(CONF_PHASE_LIMIT_L1),
                selected.get(CONF_PHASE_LIMIT_L2),
                selected.get(CONF_PHASE_LIMIT_L3),
            ],
        },
        "next_test": "Przyłącze i fazy",
    })

    readout_ok = inventory.get("odczytane_pola") == 24 and inventory.get("status") == "odczytano_6_programow"
    grid_off = inventory.get("global_grid_charge") == "off"
    enabled = inventory.get("grid_charging_programs") or []
    tou_items = []
    if readout_ok:
        tou_items.append("Odczyt 24/24 pól TOU jest poprawny.")
    else:
        tou_items.append("Mapa programów TOU jest niekompletna.")
    if grid_off:
        tou_items.append("Grid Charge jest wyłączony (obecna konfiguracja, nie awaria).")
    if not enabled:
        tou_items.append("Wszystkie programy są bez Grid/Both (obecna konfiguracja).")
    groups.append({
        "key": "tou", "title": "3. Programy Deye TOU",
        "status": "odczyt_ok" if readout_ok else "wymaga",
        "items": tou_items,
        "evidence": {
            "read_fields": inventory.get("odczytane_pola"),
            "grid_charge": inventory.get("global_grid_charge"),
            "time_of_use": inventory.get("tou_mode_raw"),
            "grid_programs": enabled,
        },
        "next_test": "Programy Deye TOU",
    })

    forecast_ok = sim.get("status") == "gotowa" and sim.get("forecast_hours") == 48
    plan_ok = plan.get("status") == "wstepny_plan"
    plan_items = []
    if not forecast_ok:
        plan_items.append("Prognoza 48h nie jest kompletna; to ogranicza automatyczne planowanie.")
    if not plan_ok:
        plan_items.append("Brak aktywnej propozycji ładowania na najbliższe okno.")
    if not plan_items:
        plan_items.append("Prognoza i wstępny plan są dostępne, lecz nie są poleceniem dla falownika.")
    groups.append({
        "key": "forecast", "title": "4. Prognoza i plan",
        "status": "odczyt_ok" if forecast_ok and plan_ok else "wymaga",
        "items": plan_items,
        "evidence": {
            "forecast_hours": sim.get("forecast_hours"),
            "simulation_status": sim.get("status"),
            "plan_status": plan.get("status"),
        },
        "next_test": "Prognoza i plan",
    })

    hardware = [
        "Niepotwierdzone limity ładowania przekazywane przez BMS i parametry toru DC.",
        "Brak testu fizycznego zapisu, odczytu zwrotnego i pomiaru reakcji Deye.",
        "Brak zweryfikowanego trwałego backupu, watchdogu i procedury przywrócenia ustawień.",
    ]
    groups.append({
        "key": "hardware", "title": "5. Bezpieczne uruchomienie",
        "status": "blokada",
        "items": hardware,
        "evidence": {
            "write_test_completed": False, "rollback_verified": False,
            "bms_limit_confirmed": False, "automatic_control": False,
        },
        "next_test": None,
    })

    notes = []
    kw = _number(inverter_limit_w)
    if kw is not None and connection_kw is not None and kw / 1000 > connection_kw:
        notes.append(
            "Deye ma konfigurowalną nastawę maksymalnego importu wyższą niż "
            "limit przyłącza. Nie wolno jej używać zamiast 15 kW i limitów faz."
        )
    if peak_shaving_state != "on":
        notes.append(
            "Peak shaving jest wyłączony lub nieznany; nastawa 8 kW "
            "nie jest aktywnym zabezpieczeniem."
        )

    if groups[0]["status"] == "wymaga":
        next_action = (
            "Uruchom „Odczyty Deye”, potem „Kierunki mocy”. "
            "Porównaj znak mocy baterii z faktycznym ładowaniem/rozładowaniem "
            "na ekranie Deye. Dopiero po takim porównaniu ustaw kierunek "
            "w opcjach zaawansowanych ESTADI."
        )
    elif not phase_ok:
        next_action = (
            "Uruchom „Przyłącze i fazy”; przypisz aktualne odczyty prądów "
            "i napięć L1/L2/L3 oraz zweryfikowane limity faz."
        )
    elif not forecast_ok:
        next_action = (
            "Sprawdź „Prognoza i plan” oraz pierwszą lukę danych PV. "
            "Nie włączaj fizycznego sterowania."
        )
    else:
        next_action = (
            "Przed fizycznym sterowaniem wymagane są dane BMS, dokładny model "
            "Deye, procedura backupu i kontrolowany test odczytu zwrotnego."
        )

    return {
        "groups": groups, "notes": notes, "next_action": next_action,
        "stage_count": len(groups),
        "readiness": "blokada",
        "commands_sent": 0,
        "control_enabled": False,
    }
