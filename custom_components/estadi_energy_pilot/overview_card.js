/* ESTADI Energy Pilot — responsive, read-only home energy cockpit.
 * All measurements come from configured Home Assistant entity IDs.
 * Never infer power flow, executed charging or grid safety from these values.
 */
(() => {
  "use strict";
  const TAG = "estadi-energy-overview-card";
  if (customElements.get(TAG)) return;

  const escape = (value) => String(value == null ? "" : value).replace(
    /[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])
  );
  const numeric = (raw) => {
    if (raw == null || raw === "" || typeof raw === "boolean") return null;
    const normalized = String(raw).trim().replace(",", ".");
    if (!normalized || /^(unknown|unavailable|none|nan|null)$/i.test(normalized)) return null;
    const n = Number(normalized);
    return Number.isFinite(n) ? n : null;
  };
  const format = (n, max = 1) => n == null ? "—" : n.toLocaleString("pl-PL", {
    maximumFractionDigits: max
  });
  const reading = (n, unit, decimal = 1) => ({
    text: format(n, decimal), unit: n == null ? "" : unit
  });
  const power = (w) => w == null ? reading(null, "") :
    Math.abs(w) >= 1000 ? reading(w / 1000, "kW", 2) : reading(w, "W", 0);
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

  class EnergyOverview extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({mode: "open"});
      this._hass = null;
      this._config = {};
      this._signature = null;
    }
    static getStubConfig() { return {}; }
    getCardSize() { return 11; }
    getGridOptions() { return {columns: "full", rows: "auto"}; }
    setConfig(config) {
      this._config = config || {};
      this._signature = null;
      this._render();
    }
    set hass(hass) {
      this._hass = hass;
      if (!hass || !hass.states) return;
      const signature = Object.keys(this._config).filter((key) =>
        key.startsWith("entity_")).map((key) => {
        const state = hass.states[this._config[key]];
        return key + ":" + (state ? state.state + ":" + state.last_updated : "missing");
      }).join("|");
      if (signature !== this._signature) {
        this._signature = signature;
        this._render();
      }
    }
    _entity(key) {
      const id = this._config["entity_" + key];
      return id && this._hass && this._hass.states ?
        this._hass.states[id] || null : null;
    }
    _state(key) { return this._entity(key)?.state ?? null; }
    _num(key, lo = -Infinity, hi = Infinity) {
      const value = numeric(this._state(key));
      return value != null && value >= lo && value <= hi ? value : null;
    }
    _value(value) {
      return '<span class="number">' + escape(value.text) +
        (value.unit ? '<small>' + escape(value.unit) + '</small>' : "") + '</span>';
    }
    _stat(title, icon, color, value, detail) {
      return '<article class="stat"><div class="stat-name"><span class="stat-icon ' +
        color + '"><ha-icon icon="' + icon + '"></ha-icon></span><span>' +
        escape(title) + '</span></div>' +
        '<div class="stat-reading">' + this._value(value) + '</div>' +
        '<div class="stat-detail">' + escape(detail) + '</div></article>';
    }
    _bar(label, readingText, width, cssClass) {
      return '<div class="bar-line"><span>' + escape(label) + '</span><strong>' +
        escape(readingText) + '</strong></div>' +
        '<div class="bar-track" role="img" aria-label="' +
        escape(label + ": " + readingText) + '"><div class="bar-fill ' + cssClass +
        '" style="width:' + clamp(width, 0, 100) + '%"></div></div>';
    }
    _render() {
      if (!this.shadowRoot) return;
      const pv = this._num("pv", 0);
      const home = this._num("home", 0);
      const soc = this._num("soc", 0, 100);
      const ev = this._num("ev", 0);
      const pump = this._num("pump", 0);
      const importKw = this._num("grid_import", 0);
      const limit = this._num("grid_limit", 0.001);
      const headroom = this._num("grid_headroom");
      const charge = this._num("smart_charge_power", 0);
      const target = this._num("smart_charge_target", 0, 100);
      const zone = this._state("tariff_zone");
      const nextCheap = this._state("next_cheap");
      const health = this._state("health_status");
      const guard = this._state("grid_status");
      const healthDetails = this._entity("health_status")?.attributes || {};
      const age = numeric(healthDetails.wiek_odswiezenia_s);
      const stale = age !== null && age > 1800;
      const healthy = health === "Działa" && !stale;
      const guardUnconfirmed = !guard || guard === "unknown" || guard === "unavailable" ||
        /blokad|brak|niezn|fail|error|stop|niesprawdz/i.test(guard);
      const gridUnconfirmed = guardUnconfirmed || importKw === null || limit === null;
      const problem = !healthy || gridUnconfirmed;
      const healthLabel = stale ? "Odczyty mogą być nieaktualne" :
        healthy ? "System działa" :
        !health || health === "unknown" || health === "unavailable" ?
          "Stan systemu nieznany" : "System: " + health;
      const note = healthDetails.przyczyna != null ? String(healthDetails.przyczyna) : "";
      const date = nextCheap && nextCheap !== "unknown" && nextCheap !== "unavailable" ?
        new Date(nextCheap) : null;
      const time = date && Number.isFinite(date.getTime()) ? date.toLocaleString("pl-PL", {
        timeZone: "Europe/Warsaw", day: "2-digit", month: "2-digit",
        hour: "2-digit", minute: "2-digit"
      }) : "—";
      const scale = Math.max(1, pv || 0, home || 0);
      const pvShare = pv === null ? 0 : 100 * pv / scale;
      const homeShare = home === null ? 0 : 100 * home / scale;
      const evShare = home > 0 && ev !== null ? clamp(100 * ev / home, 0, 100) : 0;
      const pumpShare = home > 0 && pump !== null ?
        clamp(100 * pump / home, 0, 100 - evShare) : 0;
      const remainder = clamp(100 - evShare - pumpShare, 0, 100);
      const gridPct = importKw !== null && limit !== null ?
        clamp(100 * importKw / limit, 0, 100) : 0;
      const socPct = soc == null ? 0 : soc;
      const socText = soc === null ? "—" : format(soc, 0) + "%";
      const gridLimitText = limit === null ? "—" : format(limit, 2) + " kW";
      const gridImportText = importKw === null ? "—" : format(importKw, 2) + " kW";
      const guardLabel = guard && guard !== "unknown" && guard !== "unavailable" ?
        String(guard) : "brak potwierdzonego odczytu";
      const validSources = pv !== null && home !== null;

      if (this._config.mode === "compact") {
        const miniMetric = (name, readingValue) =>
          '<div class="cell"><span>' + escape(name) + '</span><strong>' +
          escape(readingValue.text) +
          (readingValue.unit ? '<small>' + escape(readingValue.unit) + '</small>' : '') +
          '</strong></div>';
        this.shadowRoot.innerHTML =
          '<style>:host{display:block;color:var(--primary-text-color,#17212b);font:inherit}' +
          '*{box-sizing:border-box}ha-card{max-width:560px;margin:0 auto;border-radius:19px;' +
          'background:var(--ha-card-background,var(--card-background-color,#fff));' +
          'border:1px solid var(--divider-color,#e2e8ef);overflow:hidden}' +
          '.head{background:linear-gradient(110deg,#123934,#1a544a);padding:18px 20px;color:#fff}' +
          '.brand{font-size:10px;letter-spacing:.16em;color:#a7e5cc;font-weight:750}' +
          '.title{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:7px}' +
          '.title strong{font-size:19px;letter-spacing:-.03em}.state{font-size:11px;border-radius:20px;' +
          'padding:6px 10px;background:#ffffff17;text-align:right;max-width:150px;line-height:1.35}' +
          '.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:' +
          'var(--divider-color,#e2e8ef)}.cell{padding:15px 18px;background:' +
          'var(--ha-card-background,var(--card-background-color,#fff));min-width:0}' +
          '.cell span{font-size:12px;color:var(--secondary-text-color,#627185);display:block}' +
          '.cell strong{font-size:23px;letter-spacing:-.035em;display:block;margin-top:5px;' +
          'font-variant-numeric:tabular-nums;white-space:nowrap}' +
          '.cell small{font-size:12px;margin-left:5px;color:var(--secondary-text-color,#627185);' +
          'font-weight:500}.foot{font-size:11px;color:var(--secondary-text-color,#627185);' +
          'padding:12px 18px;line-height:1.5}.warn{color:#bb812d}' +
          '@media(max-width:380px){.head{padding:15px}.cell{padding:12px}' +
          '.cell strong{font-size:20px}.title strong{font-size:17px}}' +
          '</style><ha-card><div class="head"><div class="brand">ESTADI / ENERGY PILOT</div>' +
          '<div class="title"><strong>Energia w skrócie</strong><span class="state">' +
          escape(problem ? "⚠ Wymaga uwagi" : "● System działa") +
          '</span></div></div><div class="grid">' +
          miniMetric("Produkcja PV", power(pv)) +
          miniMetric("Zużycie domu", power(home)) +
          miniMetric("Magazyn SOC", reading(soc, "%", 0)) +
          miniMetric("Import sieci", reading(importKw, "kW", 2)) +
          '</div><div class="foot' + (gridUnconfirmed ? ' warn' : '') + '">' +
          (gridUnconfirmed ?
            'Grid Guard: niepotwierdzony. Brak odczytu nie oznacza 0 kW. ' : '') +
          'Deye Load zawiera samochód i pompę. Sterowanie Deye jest wyłączone.' +
          '</div></ha-card>';
        return;
      }

      this.shadowRoot.innerHTML =
        '<style>' +
        ':host{display:block;color:var(--primary-text-color,#162032);font:inherit;--border:var(--divider-color,#e4e9ef);' +
        '--muted:var(--secondary-text-color,#667589);--surface:var(--ha-card-background,var(--card-background-color,#fff));' +
        '--subtle:var(--secondary-background-color,#f2f5f7)}' +
        '*{box-sizing:border-box}ha-card{display:block;border:0;box-shadow:none;background:transparent}' +
        '.shell{max-width:1450px;margin:0 auto;padding:clamp(8px,2vw,28px);display:grid;gap:16px}' +
        '.hero{min-height:210px;background:linear-gradient(118deg,#102c31,#103d3c 65%,#1a4b3c);color:#f6fffc;' +
        'border-radius:26px;position:relative;overflow:hidden;padding:clamp(25px,3vw,42px);display:flex;' +
        'align-items:center;justify-content:space-between;gap:24px}' +
        '.hero:before{content:"";position:absolute;width:320px;height:320px;border:1px solid #ffffff21;' +
        'border-radius:50%;right:22px;top:-124px;box-shadow:0 0 0 48px #ffffff07,0 0 0 98px #ffffff04;pointer-events:none}' +
        '.hero-copy{z-index:1}.eyebrow{color:#7fdfc2;font-size:11px;letter-spacing:.17em;font-weight:750}' +
        'h1{font-size:clamp(29px,3.2vw,48px);letter-spacing:-.05em;line-height:1.05;margin:14px 0 12px;font-weight:750}' +
        '.subtitle{color:#c4dad8;line-height:1.6;font-size:14px;max-width:580px;margin:0 0 18px}' +
        '.chips{display:flex;gap:9px;flex-wrap:wrap}.chip{border:1px solid #ffffff38;border-radius:99px;padding:7px 11px;' +
        'font-size:12px;background:#ffffff12;color:#f4fffc;display:inline-flex;gap:7px;align-items:center}' +
        '.chip ha-icon{--mdc-icon-size:15px}.gauge{z-index:1;width:152px;height:152px;flex:0 0 152px;' +
        'border-radius:50%;display:grid;place-items:center;background:conic-gradient(#7de7b4 var(--soc),#ffffff18 0);' +
        'box-shadow:0 20px 60px #031b1d66;position:relative}' +
        '.gauge:after{content:"";position:absolute;inset:12px;background:#143933;border-radius:50%}' +
        '.gauge-inside{z-index:1;text-align:center;display:grid;gap:3px}.gauge-inside span{font-size:32px;' +
        'letter-spacing:-.05em;font-weight:790}.gauge-inside small{font-size:11px;color:#b6d5c9}' +
        '.gauge.unknown{background:conic-gradient(#819895 var(--soc),#ffffff18 0)}' +
        '.status{border-radius:15px;display:flex;align-items:flex-start;gap:12px;padding:14px 17px;' +
        'background:var(--surface);border:1px solid var(--border);font-size:13px;line-height:1.5}' +
        '.status ha-icon{--mdc-icon-size:22px;color:#0b9b74;flex:none}.status.warning{border-color:#e4b67b;' +
        'background:rgba(218,145,42,.07)}.status.warning ha-icon{color:#c38127}' +
        '.status b{display:block;font-size:14px;margin-bottom:2px}.status small{font-size:12px;color:var(--muted)}' +
        '.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}' +
        '.stat,.panel{background:var(--surface);border:1px solid var(--border);border-radius:21px;min-width:0}' +
        '.stat{padding:19px 20px;min-height:150px}.stat-name{display:flex;align-items:center;gap:10px;' +
        'font-size:13px;font-weight:650;color:var(--muted)}.stat-icon{width:35px;height:35px;border-radius:11px;' +
        'display:grid;place-items:center;flex:none}.stat-icon ha-icon{--mdc-icon-size:20px}' +
        '.sun{background:#fff0d3;color:#b87514}.house{background:#d9f3f5;color:#167e8f}' +
        '.battery{background:#dcf6e8;color:#18845c}.grid{background:#ebe6f9;color:#6955b5}' +
        '.stat-reading{font-variant-numeric:tabular-nums;margin-top:17px}.stat-reading .number{font-size:' +
        'clamp(27px,2.8vw,38px);font-weight:770;letter-spacing:-.055em;white-space:nowrap}' +
        '.number small{font-size:14px;color:var(--muted);font-weight:550;margin-left:6px;letter-spacing:0}' +
        '.stat-detail{font-size:11px;color:var(--muted);margin-top:6px;line-height:1.45}' +
        '.panels{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr);gap:14px}' +
        '.panel{padding:clamp(18px,2vw,25px)}.panel h2{font-size:18px;font-weight:730;letter-spacing:-.02em;margin:0 0 15px}' +
        '.balance{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,1fr) minmax(230px,.52fr);' +
        'align-items:center;gap:28px}.bar-line{display:flex;justify-content:space-between;align-items:center;' +
        'gap:12px;font-size:13px;margin:16px 0 9px}.bar-line strong{font-variant-numeric:tabular-nums}' +
        '.bar-track{height:14px;border-radius:20px;background:var(--subtle);overflow:hidden}' +
        '.bar-fill{height:100%;border-radius:20px;transition:width .25s ease-out}' +
        '.solar-fill{background:linear-gradient(90deg,#ffc967,#f2a326)}' +
        '.house-fill{background:linear-gradient(90deg,#5ec5cf,#248ba9)}' +
        '.usage{height:13px;border-radius:20px;background:var(--subtle);overflow:hidden;display:flex;margin-top:9px}' +
        '.usage span{height:100%}.usage .ev{background:#7486d5}.usage .pump{background:#44b5a2}' +
        '.usage .rest{background:#b9cdd1}.legend{display:flex;flex-wrap:wrap;gap:7px 18px;color:var(--muted);' +
        'font-size:11px;margin-top:10px}.legend i{width:8px;height:8px;display:inline-block;border-radius:50%;' +
        'background:#7486d5;margin-right:5px}.legend .pump-dot{background:#44b5a2}' +
        '.legend .rest-dot{background:#b9cdd1}.aside{background:var(--subtle);padding:20px;border-radius:16px;' +
        'font-size:13px;line-height:1.65}.aside b{display:block;font-size:15px;margin-bottom:7px}' +
        '.aside p{margin:0;color:var(--muted)}.line{display:flex;align-items:center;justify-content:space-between;' +
        'gap:12px;padding:13px 0;border-bottom:1px solid var(--border);font-size:13px;line-height:1.5}' +
        '.line:last-child{border-bottom:0}.line strong{text-align:right;max-width:55%;font-size:14px;' +
        'font-weight:680;overflow-wrap:anywhere}.progress{height:11px;background:var(--subtle);border-radius:30px;' +
        'overflow:hidden}.progress>i{display:block;height:100%;background:#46b88c;border-radius:30px}' +
        '.progress.grid-progress>i{background:#6d89ca}.track-title{display:flex;justify-content:space-between;' +
        'gap:12px;margin:12px 0 10px;font-size:13px}.track-title strong{font-variant-numeric:tabular-nums}' +
        '.twocol{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:19px}' +
        '.mini{border-radius:14px;background:var(--subtle);padding:14px;min-width:0}' +
        '.mini span{display:block;font-size:11px;color:var(--muted);margin-bottom:6px}' +
        '.mini strong{font-size:19px;font-variant-numeric:tabular-nums}' +
        '.hint{font-size:12px;color:var(--muted);line-height:1.6;margin:13px 0 0}' +
        '.attention{color:#b87922}.empty{color:var(--muted);font-size:12px;font-style:italic}' +
        '@media(max-width:970px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}' +
        '.panels{grid-template-columns:1fr}.balance{grid-template-columns:1fr;gap:12px}}' +
        '@media(max-width:560px){.shell{padding:6px;gap:10px}.hero{padding:23px;border-radius:20px;min-height:0}' +
        '.hero:before{right:-180px}.gauge{width:92px;height:92px;flex-basis:92px}.gauge:after{inset:8px}' +
        '.gauge-inside span{font-size:21px}.gauge-inside small{font-size:9px}' +
        '.hero{gap:7px}.eyebrow{font-size:10px}.subtitle{font-size:12px;margin-bottom:12px}' +
        '.chips{gap:5px}.chip{font-size:10px;padding:6px 8px}.hero h1{font-size:30px}' +
        '.metrics{gap:9px}.stat{padding:15px;min-height:130px;border-radius:17px}' +
        '.stat-name{font-size:11px;gap:6px}.stat-icon{width:28px;height:28px;border-radius:9px}' +
        '.stat-icon ha-icon{--mdc-icon-size:16px}.stat-reading .number{font-size:26px}' +
        '.number small{font-size:11px;margin-left:4px}.panel{border-radius:17px;padding:17px}' +
        '.twocol{gap:8px}.mini{padding:12px}.mini strong{font-size:16px}.status{padding:12px}}' +
        '@media(max-width:355px){.gauge{display:none}.stat-reading .number{font-size:23px}}' +
        '@media(prefers-reduced-motion:reduce){.bar-fill{transition:none}}' +
        '</style>' +
        '<ha-card><main class="shell">' +
        '<header class="hero"><div class="hero-copy"><div class="eyebrow">ESTADI / ENERGY PILOT</div>' +
        '<h1>Energia w Twoim domu.</h1>' +
        '<p class="subtitle">Bieżące pomiary, magazyn i planowanie taryfowe. Wszystko czytelnie, w jednym miejscu.</p>' +
        '<div class="chips"><span class="chip"><ha-icon icon="mdi:shield-lock-outline"></ha-icon>' +
        'Tryb doradczy</span><span class="chip">Sterowanie Deye: wyłączone</span></div></div>' +
        '<div class="gauge ' + (soc === null ? 'unknown' : '') + '" style="--soc:' +
        socPct + '%" role="img" aria-label="Stan magazynu: ' + escape(socText) +
        '"><div class="gauge-inside"><span>' + escape(socText) + '</span><small>Magazyn SOC</small></div></div>' +
        '</header>' +
        '<div class="status ' + (problem ? 'warning' : '') + '" role="status">' +
        '<ha-icon icon="' + (problem ? 'mdi:alert-circle-outline' : 'mdi:check-circle-outline') +
        '"></ha-icon><div><b>' + escape(healthLabel) + (gridUnconfirmed ? ' · Grid Guard wymaga weryfikacji' : '') +
        '</b><small>' + (problem ?
          'Wskazania są doradcze. Brak kalibracji lub pomiaru nie jest zerowym poborem.' :
          'Odczyty aktywne; wizualny wskaźnik nie zastępuje zabezpieczeń fizycznych.') +
        '</small>' + (note && !healthy ? '<div class="hint">' + escape(note) + '</div>' : '') +
        '</div></div>' +
        '<section class="metrics" aria-label="Najważniejsze odczyty">' +
        this._stat('Fotowoltaika', 'mdi:solar-power', 'sun', power(pv), 'Produkcja chwilowa') +
        this._stat('Cały dom', 'mdi:home-lightning-bolt-outline', 'house', power(home),
          'Deye Load · zawiera EV i pompę') +
        this._stat('Magazyn', 'mdi:battery-80', 'battery', reading(soc, '%', 0),
          'Aktualny SOC') +
        this._stat('Sieć · import', 'mdi:transmission-tower', 'grid', reading(importKw, 'kW', 2),
          gridUnconfirmed ? 'Pomiar wymaga weryfikacji' : 'Potwierdzony pomiar Grid Guard') +
        '</section><section class="panels">' +
        '<article class="panel balance"><div><h2>Bilans chwilowy</h2>' +
        this._bar('Fotowoltaika', power(pv).text + ' ' + power(pv).unit, pvShare, 'solar-fill') +
        this._bar('Pobór Deye Load', power(home).text + ' ' + power(home).unit, homeShare, 'house-fill') +
        (validSources ? '<div class="usage" aria-label="Udziały znanych odbiorników w Deye Load">' +
          '<span class="ev" style="width:' + evShare + '%"></span>' +
          '<span class="pump" style="width:' + pumpShare + '%"></span>' +
          '<span class="rest" style="width:' + remainder + '%"></span></div>' :
          '<div class="hint">Brak pełnego odczytu mocy.</div>') +
        '<div class="legend"><span><i></i>EV</span><span><i class="pump-dot"></i>Pompa</span>' +
        '<span><i class="rest-dot"></i>Reszta domu</span></div></div>' +
        '<div class="aside"><b>Jak czytać bilans?</b><p>To porównanie mocy chwilowych, ' +
        'nie wyliczenie kierunków przepływu. Nie przypisujemy energii do źródeł, ' +
        'dopóki pomiary sieci i magazynu nie są potwierdzone. EV i pompa są już w Deye Load.</p></div></article>' +
        '<article class="panel"><h2>Magazyn i przyłącze</h2>' +
        '<div class="track-title"><span>Poziom magazynu</span><strong>' + escape(socText) + '</strong></div>' +
        '<div class="progress" role="img" aria-label="SOC magazynu: ' + escape(socText) +
        '"><i style="width:' + socPct + '%"></i></div>' +
        '<div class="track-title"><span>Import względem limitu</span><strong>' +
        escape(gridImportText) + ' / ' + escape(gridLimitText) + '</strong></div>' +
        '<div class="progress grid-progress" role="img" aria-label="Obciążenie przyłącza: ' +
        escape(gridImportText) + ' z limitu ' + escape(gridLimitText) + '">' +
        '<i style="width:' + gridPct + '%"></i></div>' +
        '<p class="hint ' + (gridUnconfirmed ? 'attention' : '') + '">Grid Guard: ' + escape(guardLabel) +
        '. Dostępny zapas: ' + escape(headroom == null ? '—' : format(headroom, 2) + ' kW') +
        '. To podgląd, nie fizyczne ograniczenie mocy.</p>' +
        '<div class="twocol"><div class="mini"><span>Samochód EV</span><strong>' +
        escape(power(ev).text) + ' ' + escape(power(ev).unit) + '</strong></div>' +
        '<div class="mini"><span>Pompa ciepła</span><strong>' +
        escape(power(pump).text) + ' ' + escape(power(pump).unit) + '</strong></div></div></article>' +
        '<article class="panel"><h2>Plan ładowania</h2>' +
        '<div class="line"><span>Stan systemu</span><strong>' + escape(healthLabel) + '</strong></div>' +
        '<div class="line"><span>Taryfa</span><strong>' +
        escape(zone === 'cheap' ? 'Tania strefa' :
          zone === 'peak' || zone === 'evening' ? 'Droższa strefa' : 'Nieznana strefa') +
        '</strong></div>' +
        '<div class="line"><span>Następne tanie okno</span><strong>' + escape(time) + '</strong></div>' +
        '<div class="line"><span>Sugerowana moc</span><strong>' +
        escape(charge === null ? '—' : format(charge, 2) + ' kW') + '</strong></div>' +
        '<div class="line"><span>Docelowy SOC</span><strong>' +
        escape(target === null ? '—' : format(target, 0) + '%') + '</strong></div>' +
        '<p class="hint">Propozycja nie została wysłana do falownika. ' +
        'Prognoza 48h, koszty i dane serwisowe znajdują się w pozostałych zakładkach.</p>' +
        '</article></section></main></ha-card>';
    }
  }
  customElements.define(TAG, EnergyOverview);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((item) => item.type === TAG)) {
    window.customCards.push({
      type: TAG, name: "ESTADI — Centrum energii",
      description: "Responsywny bilans PV, Deye Load, magazynu i sieci; bez sterowania",
      preview: true
    });
  }
})();