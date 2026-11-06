"""Grid-connection headroom advisor — never writes inverter settings.

P_grid is the measured whole-site import, already containing EV, heat pump
and current battery charging. Do not subtract these consumers twice.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class GridDecision:
    state: str
    import_kw: float | None
    soft_limit_kw: float
    connection_limit_kw: float
    current_charge_kw: float | None
    allowed_charge_kw: float | None
    headroom_kw: float | None
    reason: str
    phase_checked: bool
    automatic_ready: bool = False

    def as_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def _num(value: float | None) -> float | None:
    try:
        x = float(value)
        return x if isfinite(x) else None
    except (ValueError, TypeError):
        return None


def calculate_grid_guard(
    grid_power_w: float | None,
    battery_charging_w: float | None,
    *,
    import_sign: int = 0,
    connection_limit_kw: float = 15.0,
    reserve_kw: float = 2.0,
    battery_max_kw: float = 10.0,
    phase_currents_a: tuple[float | None, float | None, float | None] | None = None,
    phase_limits_a: tuple[float, float, float] | None = None,
    phase_voltages_v: tuple[float, float, float] | None = None,
) -> GridDecision:
    """Suggest a *non-executable* cap; phase data are mandatory for automation.

    import_sign 1 means positive grid measurement is importing, -1 reverse,
    0 means polarity has not been verified. The reserve buffers sudden loads,
    not a replacement for electrical overcurrent protections.
    """
    if not 0 < connection_limit_kw <= 100 or not 0 <= reserve_kw < connection_limit_kw or not 0 <= battery_max_kw <= 100:
        raise ValueError("Niewłaściwy limit mocy lub rezerwy")
    soft = connection_limit_kw - reserve_kw

    def blocked(reason: str, imp=None, ch=None):
        return GridDecision("blokada", imp, soft, connection_limit_kw,
                            ch, None, None, reason, False)

    if import_sign not in (1, -1):
        return blocked("Niepotwierdzony znak pomiaru importu Deye")
    grid = _num(grid_power_w)
    charging = _num(battery_charging_w)
    if grid is None:
        return blocked("Brak prawidłowego pomiaru mocy na przyłączu")

    # Export values are negative; import is positive after polarity calibration.
    importing_kw = max(0.0, import_sign * grid / 1000)
    if charging is None or charging < 0:
        return GridDecision(
            "blokada", round(importing_kw, 2), soft, connection_limit_kw, None,
            None, round(soft - importing_kw, 2),
            "Import widoczny; brak potwierdzonego kierunku/mocy ładowania baterii",
            False,
        )
    charging_kw = charging / 1000
    headroom = soft - importing_kw
    candidate = max(0.0, min(battery_max_kw, charging_kw + headroom))
    phase_checked = False
    if phase_currents_a is not None and phase_limits_a is not None and phase_voltages_v is not None:
        all_values = tuple(phase_currents_a) + tuple(phase_limits_a) + tuple(phase_voltages_v)
        if all(_num(v) is not None for v in all_values):
            if all(0 <= float(current) and 0 < float(limit) <= 200 and 100 <= float(voltage) <= 300
                   for current, limit, voltage in zip(phase_currents_a, phase_limits_a, phase_voltages_v)):
                phase_checked = True
                # Additional 3-phase balanced grid charging consumes P/3 per phase.
                # Do not use without confirming actual inverter topology.
                phase_capacity = min(
                    3 * max(0.0, (lim - amp) * volt / 1000)
                    for amp, lim, volt in zip(phase_currents_a, phase_limits_a, phase_voltages_v)
                )
                candidate = min(candidate, charging_kw + phase_capacity)

    candidate = round(max(0, candidate), 2)
    reason = (
        "Moc przyłącza blisko limitu; zmniejsz lub wstrzymaj ładowanie"
        if headroom < 0
        else "Dostępny zapas mocy na przyłączu; można rozważyć większe ładowanie"
    )
    if not phase_checked:
        reason += "; brak zweryfikowanej kontroli trzech faz"
    # No execution is permitted in this version, even with measurements.
    return GridDecision("ograniczone" if candidate <= charging_kw else "zapas",
                        round(importing_kw, 2), soft, connection_limit_kw,
                        round(charging_kw, 2), candidate, round(headroom, 2),
                        reason, phase_checked, False)
