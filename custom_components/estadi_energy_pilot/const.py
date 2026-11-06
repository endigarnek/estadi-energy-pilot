"""ESTADI Energy Pilot constants."""
DOMAIN = "estadi_energy_pilot"
CONF_SOLCAST_TODAY = "solcast_today"
CONF_SOLCAST_TOMORROW = "solcast_tomorrow"
CONF_SOLCAST_DAY3 = "solcast_day3"
CONF_FORECAST_SOLAR_ENTRY = "forecast_solar_entry"
CONF_BATTERY_SOC = "battery_soc"
CONF_PV_POWER = "pv_power"
CONF_HOME_POWER = "home_power"
CONF_HEAT_PUMP_POWER = "heat_pump_power"
CONF_EV_POWER = "ev_power"
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
DEFAULTS = {
    CONF_CAPACITY: 15.0,
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
