"""Battery nominal capacity, SoH and SOC correction — pure read-only model."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class BatteryModel:
    nominal_kwh: float = 28.0
    soh_pct: float = 100.0
    minimum_soc: float = 10.0
    maximum_soc: float = 100.0
    correction_pp: float = 0.0

    def __post_init__(self):
        values = (self.nominal_kwh, self.soh_pct, self.minimum_soc,
                  self.maximum_soc, self.correction_pp)
        if not all(isfinite(v) for v in values):
            raise ValueError("Invalid battery settings")
        if not (0 < self.nominal_kwh <= 300 and 50 <= self.soh_pct <= 100
                and 0 <= self.minimum_soc < self.maximum_soc <= 100
                and -15 <= self.correction_pp <= 15):
            raise ValueError("Battery limits invalid")

    @property
    def estimated_chemical_capacity_kwh(self) -> float:
        return self.nominal_kwh * self.soh_pct / 100

    @property
    def window_energy_kwh(self) -> float:
        return self.estimated_chemical_capacity_kwh * (
            self.maximum_soc - self.minimum_soc) / 100

    def adjusted_target(self, base_soc: float) -> float:
        return min(self.maximum_soc, max(self.minimum_soc, base_soc + self.correction_pp))

    def energy_to_target_kwh(self, actual_soc: float, target_soc: float) -> float:
        if not (0 <= actual_soc <= 100 and 0 <= target_soc <= 100):
            raise ValueError("Invalid SOC")
        target = min(self.maximum_soc, max(self.minimum_soc, target_soc))
        return max(0, (target - actual_soc) / 100 * self.estimated_chemical_capacity_kwh)

    def as_dict(self) -> dict:
        return {**asdict(self),
                "estimated_capacity_kwh": round(self.estimated_chemical_capacity_kwh, 2),
                "soc_window_kwh": round(self.window_energy_kwh, 2),
                "nominal_vs_usable_warning": "Przybliżenie; potwierdź pojemność SoH/BMS"}
