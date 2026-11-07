/* ESTADI Energy Pilot — compact Deye laboratory.
 * Only invokes HA button.press for known read-only diagnostic buttons.
 * No number/select/switch service, inverter write or control enable.
 */
(() => {
  "use strict";
  const TAG = "estadi-energy-lab-card";
  if (customElements.get(TAG)) return;
  const esc = s => String(s === null || s === undefined ? "" : s)
    .replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  const plain = s => s === null || s === undefined || s === "" ? "—" : String(s);
  const TEST_LABELS = {
    meters: "Odczyty Deye", polarity: "Kierunki mocy", limits: "Przyłącze i fazy",
    forecast: "Prognoza i plan", tou: "Programy Deye TOU",
    write_capability: "Regulatory 1/2",
    write_capability_more: "Regulatory 2/2",
    charge_limits: "Nastawy ładowania", preflight: "Gotowość sterowania"
  };
  const TEST_ICON = {
    meters: "gauge", polarity: "swap-horizontal", limits: "shield-check",
    forecast: "chart-timeline-variant", tou: "clock-outline",
    write_capability: "tune", write_capability_more: "format-list-numbered",
    charge_limits: "battery-charging",
    preflight: "clipboard-check-outline"
  };
  class Lab extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({mode: "open"});
      this._config = {};
      this._hass = null;
      this._signature = "";
      this._busy = "";
      this._notice = "";
    }
    static getStubConfig() { return {result_entity: "", tests: []}; }
    getCardSize() { return 8; }
    getGridOptions() { return {columns: "full", rows: "auto"}; }
    setConfig(value) {
      if (!value || !Array.isArray(value.tests)) {
        throw new Error("Zdefiniuj testy diagnostyczne ESTADI.");
      }
      this._config = value;
      this._signature = "";
      this.render();
    }
    set hass(value) {
      this._hass = value;
      const e = value?.states?.[this._config.result_entity];
      const stamp = e ? e.state + ":" + e.last_updated + ":" +
        (e.attributes?.ostatni_test || "") : "missing";
      if (stamp !== this._signature) {
        this._signature = stamp;
        this.render();
      }
    }
    result() {
      const s = this._hass?.states?.[this._config.result_entity];
      return s?.attributes?.szczegoly || {};
    }
    _table(rows) {
      if (!rows?.length) return '<p class="empty">Nie znaleziono kandydatów. Sprawdź połączenie encji falownika i rejestr urządzeń HA.</p>';
      const table = rows.slice(0, 40).map((r, i) => {
        const range = r.domain === "number"
          ? [r.min, r.max].every(x => x !== null && x !== undefined)
            ? plain(r.min) + "–" + plain(r.max) +
              (r.step === null || r.step === undefined ? "" : " co " + plain(r.step))
            : "Zakres nieznany"
          : r.domain === "select" ? (r.options || []).slice(0, 6).join(", ") || "—" : "—";
        return '<tr><td>' + (i + 1) + '</td><td><b>' + esc(r.label || r.entity) +
          '</b><small>' + esc(r.entity) + '</small></td><td>' +
          esc(plain(r.state)) + (r.unit ? " " + esc(r.unit) : "") +
          '</td><td>' + esc(range) + '</td><td>' +
          esc(r.detected_by === "same_deye_device" ? "To samo urządzenie" : "Nazwa") + '</td></tr>';
      }).join("");
      return '<div class="tablewrap"><table><thead><tr><th>#</th><th>Regulator</th><th>Obecnie</th>'+
        '<th>Zakres / opcje</th><th>Źródło</th></tr></thead><tbody>'+table+'</tbody></table></div>';
    }
    _details(result) {
      if (!result.test) return '<p class="empty">Naciśnij test powyżej. Wynik pojawi się tutaj, bez przechodzenia do narzędzi deweloperskich.</p>';
      if (["write_capability", "write_capability_more"].includes(result.test)) {
        const count = result.discovered ?? 0;
        return '<div class="result-head"><h3>Regulatory: strona '+
          esc(result.page ?? 1)+' / '+esc(result.pages ?? 1)+' · '+esc(count)+' wszystkich</h3>'+
          '<span>Wspólne urządzenie Deye: '+esc(result.same_deye_device_count ?? 0)+'</span></div>'+
          '<p class="note">To kandydaci z Home Assistant. Odczyt zakresów nie dowodzi, że falownik przyjmie zmianę. Nie wysłano żadnych poleceń.</p>'+
          this._table(result.candidates || []) +
          (result.remaining > 0 ? '<p class="warning">Pozostało '+esc(result.remaining)+
             ' regulatorów. Uruchom „Regulatory 2/2”, aby je zobaczyć i skopiować.</p>' : '') +
          '<button class="copy" type="button" data-copy="1"><ha-icon icon="mdi:content-copy"></ha-icon> Kopiuj wykaz encji</button>';
      }
      if (result.test === "charge_limits") {
        const entries = [
          ["Prąd ładowania z sieci", result.settings?.grid_charge_current],
          ["Maks. prąd ładowania", result.settings?.max_charge_current],
          ["Limit importu ustawiony w Deye", result.settings?.max_grid_import],
          ["Próg peak shaving", result.settings?.peak_shaving]
        ];
        const table = entries.map(([label, setting]) => {
          const unit = setting?.unit || "";
          const v = setting?.value;
          const range = setting?.min_ui != null && setting?.max_ui != null ?
            String(setting.min_ui)+"–"+String(setting.max_ui) : "nieznany";
          return '<div class="limit"><span>'+esc(label)+'</span><strong>'+
              esc(v == null ? "Brak danych" : v+" "+unit)+'</strong>'+
              '<small>Konfigurowalne · zakres encji '+esc(range)+
              ' · bez potwierdzenia BMS</small></div>';
        }).join("");
        const estimated=result.approximate_dc_charge_kw_at_current_setting;
        return '<p class="note">Zakresy edycji Home Assistant nie są fizycznymi limitami BMS. '+
          'Nie wysyłamy żadnych zapisów do falownika.</p>'+
          '<div class="values limits">'+table+'</div>'+
          '<p class="note">Limit przyłącza w ESTADI: <b>'+
          esc(plain(result.contracted_connection_kw))+' kW</b>. '+
          'Orientacyjna moc DC przy bieżącej nastawie: <b>'+
          esc(estimated == null ? "brak aktualnego napięcia" : estimated+" kW")+
          '</b> — to nie limit AC ani potwierdzenie bezpieczeństwa.</p>'+
          (result.inverter_setting_above_connection_limit ?
           '<p class="warning">Nastawa maksymalnego importu w Deye jest większa '+
           'niż limit przyłącza w ESTADI. Nie podnoś jej automatycznie.</p>' : '') +
          '<p class="warning">Do aktywnego sterowania wymagane są potwierdzenie BMS, '+
          'limity faz, test fizycznego odczytu zwrotnego i cofania zmian.</p>';
      }
      if (result.test === "preflight") {
        const blockers = (result.blockers || []).map(s =>
          '<li>'+esc(s)+'</li>').join("");
        return '<h3>Warunki przed uruchomieniem fizycznego sterowania</h3>'+
          '<p class="warning">Sterowanie Deye pozostaje wyłączone. Poniższych blokad nie można omijać bez testów na urządzeniu.</p>'+
          '<ul class="blockers">'+blockers+'</ul>';
      }
      if (result.test === "forecast") {
        const values = [
          ["Dostępne godziny", result.hours === null || result.hours === undefined ? "—" : result.hours + "/48 h"],
          ["Źródło", result.source],
          ["Pokrycie godzin słonecznych", result.daylight_covered_pct == null ? "—" : result.daylight_covered_pct + "%"],
          ["Pierwsza luka", result.first_missing_daylight_at],
          ["Stan planu", result.plan_status]
        ];
        return '<div class="values">'+values.map(([label, val]) =>
          '<div><span>'+esc(label)+'</span><b>'+esc(plain(val))+'</b></div>').join("")+'</div>';
      }
      if (result.test === "meters") {
        const vals=[
          ["Sieć (ze znakiem)", result.grid_signed_kw === null ? "—" : result.grid_signed_kw+" kW"],
          ["Stan czujnika sieci", result.grid_status],
          ["Magazyn (ze znakiem)", result.battery_signed_kw === null ? "—" : result.battery_signed_kw+" kW"],
          ["Stan czujnika magazynu", result.battery_status],
          ["Encja sieci", result.grid_entity],
          ["Encja magazynu", result.battery_entity]
        ];
        return '<div class="values">'+vals.map(([key,val]) =>
          '<div><span>'+esc(key)+'</span><b>'+esc(plain(val))+'</b></div>').join("")+'</div>';
      }
      if (result.test === "limits" || result.test === "polarity") {
        const vals = Object.entries(result).filter(([key]) =>
          ["grid_status","measured_import_kw","allowed_charge_kw","headroom_kw",
           "phase_check","phase_limits_a","connection_limit_kw",
           "grid_sign","battery_charge_sign","hardware_verified"].includes(key));
        return '<div class="values">'+vals.map(([key,val]) =>
          '<div><span>'+esc(key.replace(/_/g," "))+'</span><b>'+
          esc(Array.isArray(val)?val.join(" / "):plain(val))+'</b></div>').join("")+'</div>';
      }
      if (result.test === "tou") {
        return '<p class="note">Odczytano: '+esc(plain(result.read_fields))+
          ' z 24 pól TOU. Gotowość zapisu: NIE, tylko odczyt.</p>';
      }
      return '<p class="empty">'+esc(result.reason || "Brak szczegółów")+'</p>';
    }
    copyPayload() {
      const result=this.result();
      if (!result.test) return "";
      const lines=[
        "ESTADI Energy Pilot — diagnostyka Deye (bez zapisu)",
        "Test: " + plain(result.test),
        "Sprawdzono: " + plain(result.checked_at),
        "Wynik: " + plain(result.status),
        "Przyczyna: " + plain(result.reason),
        "Wysłane polecenia do Deye: NIE",
      ];
      if(["write_capability","write_capability_more"].includes(result.test)){
        lines.push("Wykrytych kandydatów: " + plain(result.discovered));
        lines.push("Strona: " + plain(result.page || 1) +
          " / " + plain(result.pages || 1));
        for(const c of result.candidates || []){
          lines.push([c.entity,c.label,"obecnie="+plain(c.state),
            "typ="+plain(c.domain),"jednostka="+plain(c.unit),
            "min="+plain(c.min),"max="+plain(c.max),"krok="+plain(c.step),
            "opcje="+(c.options||[]).join("|"),
            "źródło="+plain(c.detected_by)].join(" ; "));
        }
      } else if(result.test==="charge_limits") {
        lines.push("Limit przyłącza (ESTADI): "+plain(result.contracted_connection_kw)+" kW");
        lines.push("Przybliżona moc DC przy bieżącym ustawieniu: "+
          plain(result.approximate_dc_charge_kw_at_current_setting)+" kW");
        for(const [k,v] of Object.entries(result.settings||{})){
          lines.push(k+": "+plain(v.value)+" "+plain(v.unit)+
            " ; zakres UI="+plain(v.min_ui)+"–"+plain(v.max_ui)+
            " ; nastawa konfigurowalna, bez potwierdzenia BMS");
        }
      } else if(result.test==="preflight") {
        for(const blocker of result.blockers || []) lines.push("BLOKADA: "+blocker);
      }
      return lines.join("\n");
    }
    async trigger(key) {
      if (this._busy) return;
      const configured=(this._config.tests || []).find(x=>x.key===key);
      if(!configured?.entity_id || !/^button\.[a-z0-9_]+$/.test(configured.entity_id)) return;
      this._busy=key;
      this._notice="";
      this.render();
      try {
        await this._hass.callService("button","press",{entity_id:configured.entity_id});
      } catch (e) {
        this._notice="Nie udało się uruchomić testu: "+String(e?.message||e);
      } finally {
        this._busy="";
        this.render();
      }
    }
    async copy() {
      const text=this.copyPayload();
      if(!text) return;
      try {
        if(!navigator.clipboard?.writeText) throw new Error("Schowek niedostępny");
        await navigator.clipboard.writeText(text);
        this._notice="Skopiowano wynik do schowka — wklej go do rozmowy.";
      } catch {
        this._notice="Przeglądarka nie udostępnia schowka. Zaznacz tekst z tabeli lub skorzystaj z HTTPS.";
      }
      this.render();
    }
    render() {
      const result=this.result();
      const buttons=(this._config.tests||[]).filter(t=>t?.key && t.entity_id).map(t=>
        '<button type="button" class="test" data-test="'+esc(t.key)+'"'+
        (this._busy ? ' disabled' : '')+'><ha-icon icon="mdi:'+esc(TEST_ICON[t.key]||"flask-outline")+'"></ha-icon>'+
        '<span>'+esc(TEST_LABELS[t.key]||t.key)+'</span></button>').join("");
      const stamp=result.checked_at||null;
      const css=[
        ':host{--surface:var(--ha-card-background,var(--card-background-color,#fff));'+
        '--soft:var(--secondary-background-color,#f4f7f8);--line:var(--divider-color,#e2e8ea);'+
        '--text:var(--primary-text-color,#1c2a32);--muted:var(--secondary-text-color,#677986);font:inherit;display:block;color:var(--text)}',
        '*{box-sizing:border-box}ha-card{display:block;border:1px solid var(--line);border-radius:17px;padding:16px;background:var(--surface);box-shadow:none}',
        '.head{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}',
        'h2{font-size:18px;margin:0;letter-spacing:-.02em}h3{font-size:14px;margin:0}',
        '.sub,.note,.empty{font-size:12px;color:var(--muted);line-height:1.55;margin:8px 0}',
        '.safe{font-size:11px;color:#187e64;border:1px solid #92cabb;padding:7px 10px;border-radius:50px;white-space:nowrap}',
        '.tests{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:14px 0}',
        '.test,.copy{cursor:pointer;display:flex;align-items:center;gap:7px;text-align:left;border:1px solid var(--line);background:var(--soft);'+
        'border-radius:10px;padding:12px;color:var(--text);font:inherit;font-size:12px;font-weight:650;min-width:0}',
        '.test:hover,.copy:hover{border-color:#28a680}.test[disabled]{opacity:.55;cursor:wait}',
        '.test span{overflow-wrap:anywhere}.test ha-icon,.copy ha-icon{--mdc-icon-size:18px;color:#229b7b}',
        '.result{border-top:1px solid var(--line);padding-top:13px}',
        '.result-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}',
        '.result-head span{font-size:11px;color:var(--muted)}',
        '.status{font-size:12px;font-weight:750}.status.ok{color:#16876b}.status.blokada{color:#c18433}.status.blad{color:#c94a43}',
        '.reason{font-size:12px;color:var(--muted);margin:6px 0 12px;line-height:1.5;overflow-wrap:anywhere}',
        '.tablewrap{overflow:auto;max-height:350px;border:1px solid var(--line);border-radius:10px;margin-top:10px}',
        'table{width:100%;border-collapse:collapse;font-size:11px}th,td{padding:10px 11px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}',
        'th{position:sticky;top:0;background:var(--surface);color:var(--muted);white-space:nowrap}',
        'td b{font-size:11px;display:block;max-width:270px}td small{font-size:10px;display:block;color:var(--muted);margin-top:3px;overflow-wrap:anywhere;max-width:290px}',
        '.copy{margin-top:11px;background:var(--surface);color:#198368}.warning{font-size:12px;color:#b78334;line-height:1.5}',
        '.values{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.values div{padding:10px;background:var(--soft);border-radius:9px;min-width:0}',
        '.values span{display:block;font-size:10px;color:var(--muted)}.values b{font-size:12px;display:block;margin-top:6px;overflow-wrap:anywhere}',
        '.limits .limit{background:var(--soft);padding:11px;border-radius:10px}.limit span,.limit small{display:block;font-size:11px;color:var(--muted)}.limit strong{display:block;font-size:16px;margin:5px 0}.limit small{font-size:10px}',
        '.blockers{padding-left:22px;font-size:12px;line-height:1.6}.blockers li{margin-bottom:3px}',
        '.notice{font-size:12px;color:#269775;margin-top:9px}',
        '@media(max-width:850px){.tests{grid-template-columns:repeat(2,minmax(0,1fr))}.values{grid-template-columns:repeat(2,minmax(0,1fr))}}',
        '@media(max-width:450px){ha-card{padding:11px}.test{padding:9px;font-size:11px}.safe{font-size:10px}}'
      ].join("");
      this.shadowRoot.innerHTML='<style>'+css+'</style><ha-card>'+
        '<div class="head"><h2>Laboratorium Deye</h2><span class="safe">Tylko odczyt · 0 komend do falownika</span></div>'+
        '<p class="sub">Sprawdź czujniki, ograniczenia i możliwość regulacji mocy. Każdy test opisuje wynik; nie zmienia ustawień urządzenia.</p>'+
        '<div class="tests">'+buttons+'</div><div class="result">'+
        '<div class="result-head"><h3>Ostatni wynik: '+esc(TEST_LABELS[result.test]||"Brak testu")+'</h3>'+
        '<span class="status '+esc(result.status||"")+'">'+esc(plain(result.status||"Nie uruchomiono"))+'</span></div>'+
        (stamp?'<p class="sub">'+esc(stamp)+'</p>':"")+
        (result.reason?'<p class="reason">'+esc(result.reason)+'</p>':"")+
        this._details(result)+'</div>'+
        (this._notice?'<p class="notice">'+esc(this._notice)+'</p>':"")+'</ha-card>';
      this.shadowRoot.querySelectorAll("[data-test]").forEach(b=>b.addEventListener("click",()=>
        this.trigger(b.getAttribute("data-test"))));
      const copy=this.shadowRoot.querySelector("[data-copy]");
      if(copy)copy.addEventListener("click",()=>this.copy());
    }
  }
  customElements.define(TAG,Lab);
  window.customCards=window.customCards||[];
  if(!window.customCards.some(c=>c.type===TAG)){
    window.customCards.push({type:TAG,name:"ESTADI — Laboratorium Deye",
      description:"Kompaktowe testy odczytowe i wykaz sterowania bez zmiany falownika",preview:true});
  }
})();