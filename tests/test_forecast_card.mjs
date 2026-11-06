import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import test from "node:test";

const source = fs.readFileSync(
  path.join(import.meta.dirname, "../custom_components/estadi_energy_pilot/forecast_card.js"),
  "utf8"
);
const registered = new Map();
const customElements = {
  get(name) { return registered.get(name); },
  define(name, component) { registered.set(name, component); }
};
class MockElement {
  attachShadow() {
    const listeners = {};
    this.shadowRoot = {
      innerHTML: "",
      listeners,
      addEventListener(name, fn) { listeners[name] = fn; }
    };
    return this.shadowRoot;
  }
}
const window = {};
vm.runInNewContext(source, {
  customElements, HTMLElement: MockElement, window, console, Date, Math,
  Number, String, Array, Object
});
const Card = registered.get("estadi-energy-forecast-card");
const sensorId = "sensor.renamed_by_homeassistant";

function data(count = 48) {
  return Array.from({length: count}, (_, i) => ({
    czas: new Date(Date.UTC(2026, 10, 7, 12 + i)).toISOString(),
    soc_do: 73 - i / 2,
    pv: i % 24 >= 5 && i % 24 <= 14 ? 1.5 : 0,
    dom: 1.25,
    import: 0.4,
    eksport: 0.2,
    pompa: 0.3,
    auto: i === 0 ? 1.725 : 0,
    strefa: i % 3 === 0 ? "cheap" : "peak"
  }));
}

function card(rows = data()) {
  const item = new Card();
  item.setConfig({entity: sensorId, title: "Prognoza ESTADI"});
  item.connectedCallback();
  item.hass = {states: {[sensorId]: {
    state: "gotowa",
    attributes: {harmonogram_48h: rows}
  }}};
  return item;
}

test("registers only one custom card with no third-party libraries", () => {
  assert.equal(typeof Card, "function");
  assert.equal(window.customCards.length, 1);
  assert.equal(window.customCards[0].type, "estadi-energy-forecast-card");
  vm.runInNewContext(source, {customElements, HTMLElement: MockElement, window, console});
  assert.equal(window.customCards.length, 1);
});

test("renders 48 hourly values, SOC and energy in separate units", () => {
  const item = card();
  assert.equal(item._data.length, 48);
  assert.match(item.shadowRoot.innerHTML, /Prognoza ESTADI/);
  assert.match(item.shadowRoot.innerHTML, /SV[Gg]|<svg/);
  assert.match(item.shadowRoot.innerHTML, /Lewa oś: poziom magazynu SOC/);
  assert.match(item.shadowRoot.innerHTML, /Prawa oś: energia w godzinie \(kWh\)/);
  assert.match(item.shadowRoot.innerHTML, /Deye Load zawiera EV i pompę/);
  assert.match(item.shadowRoot.innerHTML, /SYMULACJA · BEZ STEROWANIA/);
});

test("tap and keyboard select chart hour without any Home Assistant service call", () => {
  const item = card();
  item._pickPointer({
    target: {
      closest() {
        return {getBoundingClientRect() { return {left: 0, width: 900}; }};
      }
    },
    clientX: 900
  });
  assert.equal(item._active, 47);
  const listener = item.shadowRoot.listeners.keydown;
  let prevented = false;
  listener({key: "ArrowLeft", target: {closest() { return null; }},
            preventDefault() { prevented = true; }});
  assert.equal(item._active, 46);
  assert.equal(prevented, true);
  assert.match(item.shadowRoot.innerHTML, /aria-valuenow="47"/);
});

test("unknown or missing forecasts never invent zero values", () => {
  const item = card([]);
  assert.equal(item._data.length, 0);
  assert.match(item.shadowRoot.innerHTML, /Brak godzinowej prognozy/);
  assert.doesNotMatch(item.shadowRoot.innerHTML, /<path d=/);
  const withMissing = data(2);
  withMissing[1].pv = null;
  item.hass = {states: {[sensorId]: {state: "niepelna_prognoza_pv",
    attributes: {harmonogram_48h: withMissing}}}};
  assert.equal(item._data[1].pv, null);
});

test("sorts offset-aware timestamps across DST instead of local clock strings", () => {
  const rows = [
    {czas: "2026-10-25 02:00+0100", soc_do: 49, pv: 0, strefa: "cheap"},
    {czas: "2026-10-25 02:00+0200", soc_do: 50, pv: 0, strefa: "cheap"}
  ];
  const item = card(rows);
  assert.equal(item._data.length, 2);
  assert.equal(item._data[0].soc, 50);
  assert.equal(item._data[1].soc, 49);
});

test("escapes title and avoids HTML injection via forecast state", () => {
  const item = new Card();
  item.setConfig({entity: sensorId, title: '<img src=x onerror="pwned()">'});
  item.connectedCallback();
  const rows = data(2);
  rows[0].strefa = '<script>alert(1)</script>';
  item.hass = {states: {[sensorId]: {state: "gotowa",
    attributes: {harmonogram_48h: rows}}}};
  assert.doesNotMatch(item.shadowRoot.innerHTML, /<img/);
  assert.doesNotMatch(item.shadowRoot.innerHTML, /<script>/);
  assert.match(item.shadowRoot.innerHTML, /&lt;img/);
});

test("rejects invalid config and permits toggling series", () => {
  const item = new Card();
  assert.throws(() => item.setConfig({}), /wymagane ID/);
  item.setConfig({entity: sensorId, default_series: ["soc", "pv"]});
  item.connectedCallback();
  item.hass = {states: {[sensorId]: {state: "gotowa",
    attributes: {harmonogram_48h: data()}}}};
  assert.equal(item._visible.has("dom"), false);
  const before = item.shadowRoot.innerHTML;
  item.shadowRoot.listeners.click({
    target: {closest(sel) {
      return sel.includes("button") ?
        {getAttribute() { return "dom"; }} : null;
    }}
  });
  assert.equal(item._visible.has("dom"), true);
  assert.notEqual(item.shadowRoot.innerHTML, before);
});

test("does not include an inverter write path", () => {
  for (const forbidden of ["hass.callService", "number.set_value", "switch.turn_on",
                           "select.select_option", "fetch(", "XMLHttpRequest"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});

test("mobile chart uses a narrower viewBox and readable reduced tick density", () => {
  const item = card();
  assert.deepEqual([...item._visible].sort(), ["import", "pv", "soc"].sort());
  item._compact = true;
  item._draw();
  const html = item.shadowRoot.innerHTML;
  assert.match(html, /viewBox="0 0 520 290"/);
  assert.doesNotMatch(html, /min-width:670px/);
  const ticks = (html.match(/text-anchor="middle"/g) || []).length;
  assert.ok(ticks >= 3 && ticks <= 5, "mobile should show only a few time ticks");
});

test("missing series and zero energy values remain distinct", () => {
  const dataPoints = data(3);
  dataPoints[1].pv = null;
  dataPoints[2].pv = 0;
  const item = card(dataPoints);
  assert.equal(item._data[1].pv, null);
  assert.equal(item._data[2].pv, 0);
});
