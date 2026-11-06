/* ESTADI Energy Pilot — live overview; read-only Home Assistant card. */
(() => {
  "use strict";
  const TAG = "estadi-energy-overview-card";
  if (customElements.get(TAG)) return;
  const esc = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, (char) =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const number = (value) => {
    if (value === null || value === undefined || value === "" || value === "unknown" ||
        value === "unavailable") return null;
    const parsed = Number(String(value).replace(",", "."));
    return Number.isFinite(parsed) ? parsed : null;
  };
  const format = (value, places) => value === null ? "—" :
    value.toLocaleString("pl-PL", {maximumFractionDigits: places});
  const watts = (value) => {
    if (value === null) return {value:"—", unit:""};
    return Math.abs(value) >= 1000 ?
      {value:format(value / 1000, 2), unit:"kW"} :
      {value:format(value, 0), unit:"W"};
  };
  const kW = (value) => ({value: format(value, 2), unit: value === null ? "" : "kW"});
  const pct = (value) => ({value:format(value, 0), unit: value === null ? "" : "%"});
  class Overview extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({mode:"open"});
      this._config = {};
      this._hass = null;
      this._signature = "";
    }
    static getStubConfig() { return {}; }
    getCardSize() { return 12; }
    getGridOptions() { return {columns:"full", rows:"auto"}; }
    setConfig(config) {
      this._config = config || {};
      this._signature = "";
      this._render();
    }
    set hass(hass) {
      this._hass = hass;
      if (!hass || !this._config) return;
      const keys = Object.keys(this._config).filter((key) => key.startsWith("entity_"));
      const signature = keys.map((key) => {
        const s = hass.states[this._config[key]];
        return s ? this._config[key] + ":" + s.state + ":" + s.last_updated : "missing:" + key;
      }).join("|");
      if (signature !== this._signature) {
        this._signature = signature;
        this._render();
      }
    }
    _state(key) {
      const id = this._config["entity_" + key];
      return id && this._hass && this._hass.states[id] ?
        this._hass.states[id].state : null;
    }
    _num(key) { return number(this._state(key)); }
    _metric(name, symbol, data, accent, detail) {
      return '<div class="metric"><div class="metric-label"><span class="metric-icon ' +
        accent + '">' + symbol + '</span>' + esc(name) + '</div>' +
        '<div class="metric-value">' + esc(data.value) +
        '<small>' + esc(data.unit) + '</small></div><div class="metric-sub">' + esc(detail) +
        '</div></div>';
    }
    _render() {
      if (!this.shadowRoot) return;
      const soc = this._num("soc"), pv = this._num("pv"), home = this._num("home");
      const ev = this._num("ev"), pump = this._num("pump");
      const importKw = this._num("grid_import"), headroom = this._num("grid_headroom");
      const configuredLimit = this._num("grid_limit");
      const gridLimit = configuredLimit !== null && configuredLimit > 0 ? configuredLimit : null;
      const charge = this._num("smart_charge_power"), target = this._num("smart_charge_target");
      const zone = this._state("tariff_zone"), nextCheap = this._state("next_cheap");
      const health = this._state("health_status"), guard = this._state("grid_status");
      const pctSoc = soc === null ? 0 : Math.max(0, Math.min(100, soc));
      const pctGrid = importKw === null ? 0 : Math.max(0, Math.min(100, importKw / (gridLimit || 1) * 100));
      const statusText = !health || health === "unknown" || health === "unavailable" ?
        "Brak potwierdzenia odczytów" :
        /on|działa|ok|ready|true/i.test(health) ? "Odczyty aktywne" : "Sprawdź stan instalacji";
      const guardWarning = !guard || guard === "unknown" || guard === "unavailable" ||
        /blokad|brak|fail|error|stop|niesprawdz/i.test(guard);
      const guardText = !guard || guard === "unknown" || guard === "unavailable" ?
        "Brak wiarygodnego odczytu sieci" : esc(guard);
      const isCheap = zone === "cheap";
      const next = nextCheap && nextCheap !== "unknown" && nextCheap !== "unavailable" ?
        new Date(nextCheap) : null;
      const nextText = next && Number.isFinite(next.getTime()) ?
        next.toLocaleString("pl-PL",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}) : "—";
      this.shadowRoot.innerHTML =
      '<style>' +
      ':host{display:block;box-sizing:border-box;font-family:inherit;color:var(--primary-text-color,#162032)}' +
      '*{box-sizing:border-box}ha-card{background:transparent;border:0;box-shadow:none;overflow:visible}' +
      '.wrap{max-width:1500px;margin:auto;padding:clamp(12px,2vw,30px);display:grid;gap:18px}' +
      '.top{background:linear-gradient(116deg,#102e34,#11252f 58%,#163c35);color:#f3faf7;' +
      'padding:clamp(22px,3vw,40px);border-radius:25px;position:relative;overflow:hidden;display:flex;' +
      'justify-content:space-between;align-items:flex-start;gap:24px;min-height:173px}' +
      '.top:after{content:"";position:absolute;right:-60px;top:-170px;width:400px;height:400px;' +
      'border:1px solid #ffffff24;border-radius:50%;pointer-events:none;box-shadow:0 0 0 55px #ffffff08,0 0 0 110px #ffffff05}' +
      '.eyebrow{font-size:12px;letter-spacing:.19em;font-weight:700;color:#90dbc8}' +
      'h1{font-size:clamp(27px,3vw,43px);line-height:1.12;letter-spacing:-.035em;margin:12px 0 11px;font-weight:750}' +
      '.lead{font-size:14px;color:#c1d3d2;line-height:1.5;margin:0;max-width:640px}' +
      '.tag{z-index:1;border:1px solid #ffffff44;background:#ffffff14;color:#e9f8f4;border-radius:50px;' +
      'padding:11px 15px;font-size:12px;font-weight:650;white-space:nowrap}' +
      '.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}' +
      '.metric,.surface{background:var(--ha-card-background,var(--card-background-color,#fff));' +
      'border:1px solid var(--divider-color,#e5eaf0);border-radius:21px;min-width:0}' +
      '.metric{padding:20px 22px;min-height:154px}' +
      '.metric-label{display:flex;align-items:center;gap:10px;font-size:13px;font-weight:600;color:var(--secondary-text-color,#667085)}' +
      '.metric-icon{width:30px;height:30px;border-radius:11px;display:grid;place-items:center;font-size:17px;font-weight:750}' +
      '.solar{color:#b66c11;background:#f8e8cc}.home{color:#137a89;background:#d9f1f4}' +
      '.battery{color:#197455;background:#d9f5e6}.grid{color:#6350ad;background:#eae5fa}' +
      '.metric-value{font-size:clamp(26px,2.7vw,38px);font-weight:760;letter-spacing:-.04em;margin-top:17px;' +
      'font-variant-numeric:tabular-nums;white-space:nowrap}' +
      '.metric-value small{font-size:14px;margin-left:7px;color:var(--secondary-text-color,#667085);font-weight:550;letter-spacing:0}' +
      '.metric-sub{font-size:12px;color:var(--secondary-text-color,#7b8795);margin-top:4px}' +
      '.bottom{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);gap:14px}' +
      '.surface{padding:23px;min-width:0}' +
      '.surface h2{margin:0 0 18px;font-size:18px;font-weight:720;letter-spacing:-.02em}' +
      '.progress-caption{display:flex;justify-content:space-between;gap:12px;margin:14px 0 10px;font-size:13px}' +
      '.progress-caption strong{font-variant-numeric:tabular-nums}' +
      '.track{height:11px;background:var(--secondary-background-color,#eef1f5);border-radius:30px;overflow:hidden}' +
      '.fill{height:100%;border-radius:30px;background:linear-gradient(90deg,#22a06b,#77d1ab)}' +
      '.fill.gridfill{background:linear-gradient(90deg,#5883d5,#cca34a)}' +
      '.minor{font-size:12px;color:var(--secondary-text-color,#667085);line-height:1.6;margin-top:13px}' +
      '.two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px;margin-top:19px}' +
      '.small-tile{padding:15px;border-radius:15px;background:var(--secondary-background-color,#f4f6f9);min-width:0}' +
      '.small-tile label{display:block;font-size:12px;color:var(--secondary-text-color,#667085);margin-bottom:5px}' +
      '.small-tile b{font-size:19px;font-variant-numeric:tabular-nums}' +
      '.row{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:12px 0;' +
      'border-bottom:1px solid var(--divider-color,#e8edf2);font-size:13px}' +
      '.row:last-child{border-bottom:0}.row strong{text-align:right;font-size:14px}' +
      '.notice{background:var(--secondary-background-color,#f4f6f9);border-radius:14px;' +
      'padding:13px 14px;font-size:12px;line-height:1.6;margin-top:17px;color:var(--secondary-text-color,#667085)}' +
      '.warn{color:#b77b21}.statusline{font-size:13px;color:var(--secondary-text-color,#667085);margin:-3px 0 16px}' +
      '@media(max-width:900px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}' +
      '.bottom{grid-template-columns:1fr}}' +
      '@media(max-width:540px){.wrap{padding:8px;gap:11px}.top{min-height:0;padding:24px;border-radius:20px;display:block}' +
      '.tag{display:inline-block;margin-top:20px}.metrics{gap:9px}.metric{padding:15px;min-height:135px;border-radius:17px}' +
      '.metric-label{font-size:11px;gap:6px}.metric-icon{width:24px;height:24px;font-size:14px}' +
      '.metric-value{font-size:27px;margin-top:18px}.metric-value small{font-size:11px;margin-left:4px}' +
      '.surface{padding:18px;border-radius:18px}.two{gap:9px}.small-tile{padding:12px}}' +
      '</style>' +
      '<ha-card><main class="wrap">' +
      '<header class="top"><div><div class="eyebrow">ESTADI / ENERGY PILOT</div>' +
      '<h1>Energia pod kontrolą.</h1>' +
      '<p class="lead">Produkcja, zużycie, magazyn i przyłącze w jednym miejscu. ' +
      'Wszystkie wartości odświeżają się wraz z odczytami Home Assistant.</p></div>' +
      '<div class="tag">● Tryb doradczy · bez sterowania Deye</div></header>' +
      '<section class="metrics">' +
      this._metric("Fotowoltaika","☀",watts(pv),"solar","Aktualna produkcja PV") +
      this._metric("Zużycie domu","⌂",watts(home),"home","Deye Load — obejmuje EV i pompę") +
      this._metric("Magazyn energii","▰",pct(soc),"battery","Aktualny poziom naładowania") +
      this._metric("Import z sieci","↧",kW(importKw),"grid","Nieznany odczyt ≠ 0 kW") +
      '</section><section class="bottom">' +
      '<article class="surface"><h2>Magazyn i obciążenie przyłącza</h2>' +
      '<div class="progress-caption"><span>Poziom magazynu</span><strong>' + esc(pct(soc).value) + '%</strong></div>' +
      '<div class="track"><div class="fill" style="width:' + pctSoc + '%"></div></div>' +
      '<div class="progress-caption"><span>Import względem limitu przyłącza</span>' +
      '<strong>' + esc(kW(importKw).value) + ' / ' +
      esc(gridLimit === null ? '—' : format(gridLimit, 2)) + ' kW</strong></div>' +
      '<div class="track"><div class="fill gridfill" style="width:' + pctGrid + '%"></div></div>' +
      '<div class="minor ' + (guardWarning ? 'warn' : '') + '">Dostępny zapas: <strong>' + esc(kW(headroom).value) +
      (headroom === null ? '' : ' kW') + '</strong>. ' + (guardWarning ? '⚠ Grid Guard: ' : 'Grid Guard: ') + guardText +
      '. Wizualny wskaźnik nie zastępuje zabezpieczenia elektrycznego.</div>' +
      '<div class="two"><div class="small-tile"><label>Ładowanie auta</label><b>' +
      esc(watts(ev).value) + ' ' + esc(watts(ev).unit) + '</b></div>' +
      '<div class="small-tile"><label>Pompa ciepła</label><b>' +
      esc(watts(pump).value) + ' ' + esc(watts(pump).unit) + '</b></div></div>' +
      '<div class="notice">Moc samochodu i pompy już zawiera się w Deye Load. ' +
      'Nie sumujemy ich ponownie z zużyciem domu.</div></article>' +
      '<article class="surface"><h2>Plan i stan systemu</h2>' +
      '<div class="statusline">' + esc(statusText) + '</div>' +
      '<div class="row"><span>Strefa taryfy</span><strong>' +
      esc(zone === null || zone === "unknown" ? "Nieznana" : isCheap ? "Tania" : "Pozostała") +
      '</strong></div>' +
      '<div class="row"><span>Następne tanie okno</span><strong>' + esc(nextText) + '</strong></div>' +
      '<div class="row"><span>Proponowana moc ładowania</span><strong>' +
      esc(kW(charge).value) + (charge === null ? "" : " kW") + '</strong></div>' +
      '<div class="row"><span>Docelowy SOC</span><strong>' +
      esc(pct(target).value) + (target === null ? "" : "%") + '</strong></div>' +
      '<div class="notice">To jest plan doradczy, nie polecenie wysłane do falownika. ' +
      'Szczegóły prognozy 48h, ekonomii i diagnostyki są w osobnych zakładkach.</div>' +
      '</article></section></main></ha-card>';
    }
  }
  customElements.define(TAG, Overview);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === TAG)) {
    window.customCards.push({type:TAG,name:"ESTADI — centrum energii",
      description:"Nowoczesny podgląd PV, domu, magazynu, sieci i planu (tylko odczyt)",preview:true});
  }
})();