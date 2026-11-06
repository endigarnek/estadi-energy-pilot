/* ESTADI Energy Pilot v0.4.0 — self-contained read-only Lovelace forecast.
 * No external libraries, service calls, inverter writes or network fetches.
 * Values originate from attributes.harmonogram_48h of a selected HA sensor.
 */
(() => {
  "use strict";
  const COMPONENT = "estadi-energy-forecast-card";
  if (customElements.get(COMPONENT)) return;
  const SERIES = Object.freeze({
    soc: { label: "SOC", color: "#16a34a", unit: "%" },
    pv: { label: "PV", color: "#e4a00a", unit: "kWh" },
    dom: { label: "Dom razem", color: "#2563eb", unit: "kWh" },
    import: { label: "Import", color: "#dc5555", unit: "kWh" },
    eksport: { label: "Eksport", color: "#a855f7", unit: "kWh" },
    pompa: { label: "Pompa ciepła", color: "#0891b2", unit: "kWh" },
    auto: { label: "EV", color: "#64748b", unit: "kWh" },
  });
  const KEYS = Object.keys(SERIES);
  const WIDTH = 900, HEIGHT = 290, LEFT = 52, RIGHT = 58, TOP = 16, BOTTOM = 38;
  const PW = WIDTH - LEFT - RIGHT, PH = HEIGHT - TOP - BOTTOM;
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
  const num = (value) => {
    if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
    const v = Number(value);
    return Number.isFinite(v) && v >= 0 ? v : null;
  };
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  const show = (v, places = 1) => v === null ? "brak" : v.toLocaleString("pl-PL", {
    minimumFractionDigits: places, maximumFractionDigits: places
  });
  const parsed = (input) => {
    if (!Array.isArray(input)) return [];
    const out = [];
    for (const row of input.slice(0, 48)) {
      if (!row || typeof row !== "object" || typeof row.czas !== "string") continue;
      // The model sends timezone-offset-aware ISO strings, including DST.
      const epoch = Date.parse(row.czas);
      if (!Number.isFinite(epoch)) continue;
      const soc = num(row.soc_do);
      const valid = { time: epoch, czas: row.czas,
        strefa: ["cheap", "peak", "evening"].includes(row.strefa) ? row.strefa : "unknown",
        soc: soc === null || soc > 100 ? null : soc };
      for (const key of KEYS.filter((k) => k !== "soc")) valid[key] = num(row[key]);
      out.push(valid);
    }
    out.sort((a, b) => a.time - b.time);
    // Guard against duplicate timestamps; never pretend that two intervals
    // represent two different hours (DST repeats local hours with offsets).
    return out.filter((row, i) => !i || row.time !== out[i - 1].time);
  };

  class EstadiEnergyForecastCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._hass = null;
      this._config = {};
      this._visible = new Set(["soc", "pv", "dom", "import", "pompa", "auto"]);
      this._active = null;
      this._signature = null;
      this._data = [];
      this._bound = false;
    }

    static getStubConfig() {
      return { entity: "sensor.estadi_symulacja_48h_stan" };
    }

    setConfig(config) {
      if (!config || typeof config.entity !== "string" || !config.entity.startsWith("sensor.")) {
        throw new Error("ESTADI: wymagane ID encji sensora Symulacja 48h.");
      }
      const defaults = ["soc", "pv", "dom", "import", "pompa", "auto"];
      const chosen = Array.isArray(config.default_series) ?
        config.default_series.filter((key) => KEYS.includes(key)) : defaults;
      this._config = { entity: config.entity, title: config.title || "Prognoza energii 48h" };
      this._visible = new Set(chosen.length ? chosen : defaults);
      this._signature = null;
      this._draw();
    }

    set hass(value) {
      this._hass = value;
      if (!this._config.entity) return;
      const state = value?.states?.[this._config.entity];
      const raw = state?.attributes?.harmonogram_48h;
      const status = String(state?.state || "unknown");
      // Use state object identity rather than serializing every 15s update.
      const signature = state || status;
      if (signature !== this._signature) {
        this._signature = signature;
        this._data = parsed(raw);
        this._active = this._data.length ? clamp(this._active ?? 0, 0, this._data.length - 1) : null;
        this._draw();
      }
    }

    getCardSize() { return 7; }

    connectedCallback() {
      if (this._bound) return;
      this._bound = true;
      this.shadowRoot.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-series]");
        if (button) {
          const key = button.getAttribute("data-series");
          if (!SERIES[key]) return;
          if (this._visible.has(key)) this._visible.delete(key);
          else this._visible.add(key);
          this._draw();
          return;
        }
        const marker = event.target.closest("[data-point]");
        if (marker) this._choose(Number(marker.getAttribute("data-point")));
      });
      this.shadowRoot.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        if (event.target.closest("button[data-series]")) return;
        if (!this._data.length) return;
        event.preventDefault();
        if (event.key === "Home") this._choose(0);
        else if (event.key === "End") this._choose(this._data.length - 1);
        else this._choose(clamp((this._active ?? 0) + (event.key === "ArrowRight" ? 1 : -1),
                                0, this._data.length - 1));
      });
      // Touch taps select a point; mouse hover offers a live preview.
      this.shadowRoot.addEventListener("pointerdown", (event) => {
        this._pickPointer(event);
      });
      this.shadowRoot.addEventListener("pointermove", (event) => {
        if (event.pointerType !== "touch") this._pickPointer(event);
      });
    }

    _pickPointer(event) {
      if (!this._data.length || !event.target?.closest) return;
      const area = event.target.closest("[data-plot]");
      if (!area) return;
      const bounds = area.getBoundingClientRect();
      if (!bounds.width) return;
      const fraction = clamp((event.clientX - bounds.left) / bounds.width, 0, 1);
      this._choose(Math.round(fraction * (this._data.length - 1)));
    }

    _choose(index) {
      if (!Number.isInteger(index) || index < 0 || index >= this._data.length) return;
      if (index === this._active) return;
      this._active = index;
      // Redraw only the internal card, without changing state elsewhere.
      this._draw();
    }

    _draw() {
      if (!this.shadowRoot || !this._config.entity) return;
      const rows = this._data, active = clamp(this._active ?? 0, 0, Math.max(0, rows.length - 1));
      const n = rows.length;
      const x = (index) => LEFT + (n > 1 ? PW * index / (n - 1) : PW / 2);
      const maxEnergy = Math.max(1,
        ...rows.flatMap((row) => KEYS.filter((k) => k !== "soc" && this._visible.has(k))
          .map((k) => row[k] ?? 0))) * 1.12;
      const y = (key, value) => TOP + PH * (1 - value / (key === "soc" ? 100 : maxEnergy));
      const lines = [];
      for (const key of KEYS) {
        if (!this._visible.has(key)) continue;
        let part = [];
        const flush = () => {
          if (part.length) lines.push(
            '<path d="' + part.join(" ") + '" fill="none" stroke="' + SERIES[key].color +
            '" stroke-width="' + (key === "soc" ? 3.5 : 2.2) +
            '" stroke-linejoin="round" stroke-linecap="round" />');
          part = [];
        };
        rows.forEach((row, i) => {
          if (row[key] === null) { flush(); return; }
          part.push((part.length ? "L" : "M") + x(i).toFixed(2) + " " + y(key, row[key]).toFixed(2));
        });
        flush();
      }
      const shading = [];
      for (let i = 0; i < n; i++) {
        if (rows[i].strefa !== "cheap") continue;
        const cell = n > 1 ? PW / (n - 1) : PW;
        shading.push('<rect x="' + (x(i) - cell / 2).toFixed(1) +
          '" y="' + TOP + '" width="' + cell.toFixed(1) + '" height="' + PH +
          '" fill="#16a34a" opacity="0.085" />');
      }
      const grid = [];
      for (let tick = 0; tick <= 4; tick++) {
        const level = TOP + PH * tick / 4;
        grid.push('<line x1="' + LEFT + '" x2="' + (WIDTH - RIGHT) +
          '" y1="' + level + '" y2="' + level + '" stroke="currentColor" opacity=".13" />');
        grid.push('<text x="' + (LEFT - 8) + '" y="' + (level + 4) +
          '" text-anchor="end" font-size="12" fill="currentColor" opacity=".65">' +
          Math.round(100 - tick * 25) + '%</text>');
        grid.push('<text x="' + (WIDTH - RIGHT + 8) + '" y="' + (level + 4) +
          '" font-size="12" fill="currentColor" opacity=".65">' +
          show(maxEnergy * (1 - tick / 4), 1) + '</text>');
      }
      const ticks = [];
      for (let i = 0; i < n; i += Math.max(1, Math.ceil(n / 8))) {
        const moment = new Date(rows[i].time);
        const label = moment.toLocaleString("pl-PL", {
          timeZone: "Europe/Warsaw", day: "2-digit", month: "2-digit", hour: "2-digit"
        });
        ticks.push('<text x="' + x(i).toFixed(1) + '" y="' + (HEIGHT - 9) +
          '" text-anchor="middle" font-size="12" fill="currentColor" opacity=".75">' +
          escape(label) + '</text>');
      }
      const activeX = n ? x(active) : null;
      const marker = activeX === null ? "" :
        '<line x1="' + activeX + '" x2="' + activeX +
        '" y1="' + TOP + '" y2="' + (TOP + PH) +
        '" stroke="currentColor" stroke-dasharray="4 4" opacity=".6" />';
      // The invisible plot overlay is keyboard-focusable and pointer interactive.
      const svg = n ?
        '<svg role="img" aria-label="Wykres godzinowy prognozy 48 godzin, SOC na osi lewej, energia kWh na prawej" ' +
        'viewBox="0 0 ' + WIDTH + ' ' + HEIGHT + '" preserveAspectRatio="xMidYMid meet">' +
        '<g>' + shading.join("") + grid.join("") + lines.join("") + marker + ticks.join("") + '</g>' +
        '<rect data-plot tabindex="0" role="slider" aria-label="Wybór godziny prognozy" ' +
        'aria-valuemin="1" aria-valuemax="' + n + '" aria-valuenow="' + (active + 1) +
        '" x="' + LEFT + '" y="' + TOP + '" width="' + PW + '" height="' + PH +
        '" fill="transparent" />' +
        '</svg>'
        : '<div class="empty" role="status">Brak godzinowej prognozy. Sprawdź Forecast.Solar i sensor symulacji 48h.</div>';
      const selected = rows[active] || null;
      const time = selected ? new Date(selected.time).toLocaleString("pl-PL", {
        timeZone: "Europe/Warsaw", weekday: "short", day: "2-digit",
        month: "2-digit", hour: "2-digit", minute: "2-digit"
      }) : "brak";
      const info = selected ?
        '<div class="details" aria-live="polite"><strong>' + escape(time) +
        ' · ' + (selected.strefa === "cheap" ? "tania taryfa" :
          selected.strefa === "peak" ? "droższa taryfa" :
          selected.strefa === "evening" ? "strefa wieczorna" : "taryfa nieznana") +
        '</strong><div class="metrics">' +
        KEYS.map((key) => '<span><i style="background:' + SERIES[key].color + '"></i>' +
          escape(SERIES[key].label) + ': <b>' +
          escape(show(selected[key], key === "soc" ? 1 : 2)) +
          ' ' + SERIES[key].unit + '</b></span>').join("") +
        '</div></div>'
        : "";
      const legends = KEYS.map((key) =>
        '<button type="button" data-series="' + key + '" aria-pressed="' +
        (this._visible.has(key) ? "true" : "false") + '"' +
        (this._visible.has(key) ? ' class="selected"' : '') + '>' +
        '<i style="background:' + SERIES[key].color + '"></i>' +
        escape(SERIES[key].label) + '</button>'
      ).join("");
      this.shadowRoot.innerHTML =
        '<style>' +
        ':host{display:block;--fg:var(--primary-text-color,#202935);--muted:var(--secondary-text-color,#667085)}' +
        'ha-card{display:block;padding:18px 18px 15px;color:var(--fg);border-radius:16px}' +
        '.heading{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between}' +
        'h2{font-size:17px;font-weight:700;margin:0}' +
        '.tag{font-size:11px;color:var(--muted);border:1px solid var(--divider-color,#ddd);padding:4px 8px;border-radius:99px}' +
        '.legend{display:flex;flex-wrap:wrap;gap:7px;margin:15px 0 12px}' +
        'button{border:1px solid var(--divider-color,#ccc);border-radius:18px;display:flex;align-items:center;gap:6px;' +
        'background:transparent;color:var(--muted);font:inherit;font-size:12px;padding:6px 9px;cursor:pointer;opacity:.65}' +
        'button.selected{opacity:1;color:var(--fg);border-color:var(--primary-color,#16835d)}' +
        'button:focus-visible,[data-plot]:focus-visible{outline:2px solid var(--primary-color,#0088cc);outline-offset:2px}' +
        'i{display:inline-block;width:8px;height:8px;border-radius:100%;flex:none}' +
        '.scroll{overflow-x:auto;touch-action:pan-x;padding-bottom:5px}' +
        'svg{display:block;min-width:670px;width:100%;height:auto;color:var(--fg)}' +
        '.details{border-top:1px solid var(--divider-color,#ddd);padding-top:11px;font-size:13px}' +
        '.metrics{display:flex;flex-wrap:wrap;column-gap:15px;row-gap:9px;margin-top:9px}' +
        '.metrics span{display:inline-flex;align-items:center;gap:5px}.metrics b{font-variant-numeric:tabular-nums}' +
        '.note{font-size:12px;color:var(--muted);line-height:1.55;margin-top:13px}' +
        '.empty{color:var(--muted);padding:30px 10px;text-align:center}' +
        '</style><ha-card><div class="heading"><h2>' + escape(this._config.title) +
        '</h2><span class="tag">SYMULACJA · BEZ STEROWANIA</span></div>' +
        '<div class="legend" aria-label="Pokaż lub ukryj serie wykresu">' + legends + '</div>' +
        '<div class="scroll">' + svg + '</div>' + info +
        '<div class="note">Lewa oś: poziom magazynu SOC (%). Prawa oś: energia w godzinie (kWh), a nie moc chwilowa kW. ' +
        'Zielone tło: tania strefa taryfy. Dotknij wykresu lub użyj strzałek, aby wybrać godzinę. ' +
        'Deye Load zawiera EV i pompę — nie sumuj tych wartości drugi raz. ' +
        'Przyszłe sesje EV są nieznane; symulacja nie uwzględnia dodatkowego ładowania magazynu z sieci. ' +
        'Przy niepełnej prognozie nie są dopisywane zmyślone pomiary. Automatyzacja Deye jest wyłączona.</div>' +
        '</ha-card>';
    }
  }
  customElements.define(COMPONENT, EstadiEnergyForecastCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === COMPONENT)) {
    window.customCards.push({
      type: COMPONENT,
      name: "ESTADI — prognoza energii 48h",
      description: "Interaktywny wykres SOC, PV, domu, EV, pompy i importu; tylko odczyt",
      preview: true,
    });
  }
})();
