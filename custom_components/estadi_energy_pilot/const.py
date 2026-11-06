"""ESTADI Energy Pilot constants."""
DOMAIN = "estadi_energy_pilot"
INTEGRATION_VERSION = "0.3.7"
CONF_SOLCAST_TODAY = "solcast_today"
CONF_SOLCAST_TOMORROW = "solcast_tomorrow"
CONF_SOLCAST_DAY3 = "solcast_day3"
CONF_FORECAST_SOLAR_ENTRY = "forecast_solar_entry"
CONF_BATTERY_SOC = "battery_soc"
CONF_PV_POWER = "pv_power"
CONF_HOME_POWER = "home_power"
CONF_HEAT_PUMP_POWER = "heat_pump_power"
CONF_EV_POWER = "ev_power"
CONF_EV_TOPOLOGY = "ev_home_load_topology"
CONF_OUTDOOR_TEMP = "outdoor_temp"
CONF_WEATHER = "weather_entity"
CONF_CAPACITY = "battery_capacity_kwh"
CONF_BASE_W = "base_load_w"
CONF_RESERVE = "reserve_soc"
CONF_MAX_SOC = "max_soc"
CONF_PV_DISCOUNT = "pv_discount_pct"
CONF_EFFICIENCY = "roundtrip_efficiency_pct"
CONF_MARGIN = "margin_kwh"
CONF_MILD_W = "heat_pump_mild_w"
CONF_COLD_W = "heat_pump_cold_w"
CONF_NIGHT_START = "night_start"
CONF_NIGHT_END = "night_end"
CONF_MIDDAY_START = "midday_start"
CONF_AFTERNOON_END = "afternoon_end"
CONF_NOMINAL_KWH = "battery_nominal_kwh"
CONF_SOH = "battery_soh_pct"
CONF_MIN_SOC = "battery_min_soc"
CONF_USER_MAX_SOC = "battery_max_soc"
CONF_CORRECTION = "battery_reserve_correction_pp"
CONF_GRID_POWER = "grid_power"
CONF_BATTERY_POWER = "battery_power"
CONF_BATTERY_CHARGE_SIGN = "battery_charge_sign"
CONF_GRID_IMPORT_SIGN = "grid_import_sign"
CONF_GRID_LIMIT = "grid_connection_limit_kw"
CONF_GRID_BUFFER = "grid_safety_buffer_kw"
CONF_CHARGE_LIMIT = "battery_preferred_max_charge_kw"
CONF_PREFERRED_CHARGE = "battery_preferred_charge_kw"
CONF_PHASE_CURRENT_L1 = "grid_phase_current_l1"
CONF_PHASE_CURRENT_L2 = "grid_phase_current_l2"
CONF_PHASE_CURRENT_L3 = "grid_phase_current_l3"
CONF_PHASE_VOLTAGE_L1 = "grid_phase_voltage_l1"
CONF_PHASE_VOLTAGE_L2 = "grid_phase_voltage_l2"
CONF_PHASE_VOLTAGE_L3 = "grid_phase_voltage_l3"
CONF_PHASE_LIMIT_L1 = "grid_phase_limit_l1_a"
CONF_PHASE_LIMIT_L2 = "grid_phase_limit_l2_a"
CONF_PHASE_LIMIT_L3 = "grid_phase_limit_l3_a"

CONF_TARIFF = "tariff_profile"
CONF_PRICE_CHEAP = "tariff_price_cheap"
CONF_PRICE_PEAK = "tariff_price_peak"
CONF_PRICE_EVENING = "tariff_price_evening"
DEFAULTS = {
    CONF_CAPACITY: 15.0,
    CONF_EV_TOPOLOGY: "included",
    CONF_NOMINAL_KWH: 28,
    CONF_SOH: 100,
    CONF_MIN_SOC: 10,
    CONF_USER_MAX_SOC: 100,
    CONF_CORRECTION: 0,
    CONF_GRID_IMPORT_SIGN: 0,
    CONF_BATTERY_CHARGE_SIGN: 0,
    CONF_GRID_LIMIT: 15,
    CONF_PHASE_LIMIT_L1: 0,
    CONF_PHASE_LIMIT_L2: 0,
    CONF_PHASE_LIMIT_L3: 0,
    CONF_GRID_BUFFER: 2,
    CONF_CHARGE_LIMIT: 10,
    CONF_PREFERRED_CHARGE: 5,
    CONF_TARIFF: "G12w",
    CONF_PRICE_CHEAP: 0,
    CONF_PRICE_PEAK: 0,
    CONF_PRICE_EVENING: 0,
    CONF_BASE_W: 400,
    CONF_RESERVE: 20,
    CONF_MAX_SOC: 95,
    CONF_PV_DISCOUNT: 15,
    CONF_EFFICIENCY: 90,
    CONF_MARGIN: 1.0,
    CONF_MILD_W: 600,
    CONF_COLD_W: 1200,
    CONF_NIGHT_START: 21,
    CONF_NIGHT_END: 7,
    CONF_MIDDAY_START: 13,
    CONF_AFTERNOON_END: 16,
}
