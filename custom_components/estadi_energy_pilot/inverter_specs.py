"""Reference data from Deye datasheet; never infer physical limits from HA UI ranges.

IMPORTANT: Until the actual device model is *exactly* identified, the
profile is reference information, NOT a current limit for battery control.
BMS, cabling, breakers and grid connection still impose independent limits.
"""
from __future__ import annotations

# Official 2026 manufacturer document:
# https://www.deyeinverter.com/deyeinverter/2026/04/26/BDatasheetSUN-14-20K-SG05LP3-EU-SM220260424en.pdf
DATASHEET_URL = (
    "https://www.deyeinverter.com/deyeinverter/2026/04/26/"
    "BDatasheetSUN-14-20K-SG05LP3-EU-SM220260424en.pdf"
)
MANUAL_URL = (
    "https://nastechsolar.com/content/INVERTERS/DEYE/MANUAL/"
    "Manual%20SUN-%2814-20%29K-SG05LP3-EU-SM2.pdf"
)
PROFILES = {
    "SUN-14K-SG05LP3-EU-SM2": (14, 260),
    "SUN-15K-SG05LP3-EU-SM2": (15, 280),
    "SUN-16K-SG05LP3-EU-SM2": (16, 300),
    "SUN-18K-SG05LP3-EU-SM2": (18, 330),
    "SUN-20K-SG05LP3-EU-SM2": (20, 350),
}


def known_model(model: str | None) -> dict | None:
    """Only a confirmed exact Deye model matches. Generic '15kW' is NOT enough."""
    if not isinstance(model, str):
        return None
    normalized = model.strip().upper()
    if normalized.startswith("DEYE "):
        normalized = normalized[5:].strip()
    rating = PROFILES.get(normalized)
    if rating is None:
        return None
    ac_kw, battery_amps = rating
    return {
        "model": normalized,
        "rated_ac_kw": ac_kw,
        "manufacturer_max_charge_a": battery_amps,
        "manufacturer_max_discharge_a": battery_amps,
        "battery_voltage_min_v": 40,
        "battery_voltage_max_v": 60,
        "soc_tou_periods": 6,
        "source": DATASHEET_URL,
        "bms_and_installation_require_independent_validation": True,
        "auto_control_approved": False,
    }


def comparison_for_laboratory(model: str | None) -> dict:
    """Never silently turn a 350A editable UI max into hardware capability."""
    exact = known_model(model)
    return {
        "device_model_from_ha_registry": model,
        "matched_exact_official_model": bool(exact),
        "matched_datasheet_profile": exact,
        "reference_example_model": "SUN-15K-SG05LP3-EU-SM2",
        "reference_example_15kw_max_charge_a": 280,
        "reference_example_15kw_max_discharge_a": 280,
        "reference_url": DATASHEET_URL,
        "manual_url": MANUAL_URL,
        "not_a_bms_limit": True,
        "not_confirmation_of_installed_model": True,
    }
