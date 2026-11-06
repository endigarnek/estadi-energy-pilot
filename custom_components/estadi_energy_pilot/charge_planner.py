"""Read-only charging scheduler for cheap tariff windows."""
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from math import ceil
from .battery_model import BatteryModel

@dataclass(frozen=True)
class Schedule:
    state: str
    reason: str
    start: str | None = None
    finish: str | None = None
    power_kw: float | None = None
    target_soc: float | None = None
    grid_kwh: float | None = None
    alternatives: tuple = ()
    def as_dict(self):
        return asdict(self)

def propose(now: datetime, window: tuple[datetime, datetime] | None,
            soc: float | None, target: float | None, model: BatteryModel,
            grid_headroom_kw: float | None, power_limit_kw: float = 10,
            preferred_kw: float = 5, efficiency: float = 0.9) -> Schedule:
    if window is None:
        return Schedule("brak_taryfy", "Nie znam godzin taniej energii")
    if soc is None or target is None:
        return Schedule("brak_soc", "Brak bieżącego lub docelowego SOC")
    if not 0 < efficiency <= 1:
        raise ValueError("Niewłaściwa sprawność")
    target = model.adjusted_target(target)
    energy = model.energy_to_target_kwh(soc, target) / efficiency
    if energy < 0.05:
        return Schedule("gotowe", "Cel osiągnięty", target_soc=target, grid_kwh=0)
    if grid_headroom_kw is None:
        return Schedule("brak_pomiaru", "Nie znam wolnej mocy przyłącza", target_soc=target)
    max_kw = min(power_limit_kw, max(0, grid_headroom_kw))
    start, end = max(now, window[0]), window[1] - timedelta(minutes=15)
    if max_kw < 3 or start >= end:
        return Schedule("brak_mocy", "Za mało czasu lub bezpiecznej mocy", target_soc=target)
    available = (end - start).total_seconds() / 3600
    choices = []
    for power in sorted({3., 4., 5., 6., 7., 8., 9., 10., float(preferred_kw), float(max_kw)}):
        if power < 3 or power > max_kw:
            continue
        hours = energy / power
        if hours > available:
            continue
        began = end - timedelta(minutes=ceil(hours * 4) * 15)
        began = max(start, began)
        finish = began + timedelta(hours=hours)
        if finish <= end:
            choices.append((power, began, finish))
    if not choices:
        return Schedule("nieosiagalny", "Nie osiągnę celu przed końcem taniej strefy",
                        target_soc=target, grid_kwh=round(energy, 2))
    power, began, finish = min(choices, key=lambda x: abs(x[0] - preferred_kw))
    return Schedule("wstepny", "Wariant wymaga potwierdzenia BMS i taryfy",
                    began.isoformat(), finish.isoformat(), round(power, 2),
                    target, round(energy, 2),
                    tuple({"kw": p, "start": a.isoformat()} for p, a, _ in choices))
