import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";

const filepath = path.resolve("custom_components/estadi_energy_pilot/overview_card.js");
const classes = new Map();
const sandbox = {
  HTMLElement: class {
    attachShadow() {
      this.shadowRoot = {innerHTML: ""};
      return this.shadowRoot;
    }
  },
  customElements: {
    get(name) { return classes.get(name); },
    define(name, cls) { classes.set(name, cls); },
  },
  window: {customCards: []},
};
vm.runInNewContext(fs.readFileSync(filepath, "utf-8"), sandbox);
const Card = classes.get("estadi-energy-overview-card");

const fakeState = (value) => ({state:String(value),last_updated:"2026-11-06T22:30:00+01:00"});
const stateMap = (values) => Object.fromEntries(
  Object.entries(values).map(([key, value]) => ["sensor." + key, fakeState(value)])
);

const make = (values) => {
  const card = new Card();
  card.setConfig(Object.fromEntries([
    "soc", "pv", "home", "ev", "pump", "grid_import", "grid_limit",
    "grid_headroom", "grid_status", "health_status", "tariff_zone",
    "next_cheap", "smart_charge_power", "smart_charge_target",
  ].map((key) => ["entity_" + key, "sensor." + key])));
  card.hass = {states:stateMap(values)};
  return card;
};

test("overview registers a live card and read-only copy", () => {
  assert.equal(typeof Card, "function");
  const card = make({
    soc: 64, pv: 5000, home: 1532, ev: 320, pump: 846,
    grid_import: 2.4, grid_limit: 15, grid_headroom: 11.6,
    grid_status: "ok", health_status: "on", tariff_zone: "cheap",
  });
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /5 kW/);
  assert.match(html, /1,53/);
  assert.match(html, /15 kW/);
  assert.match(html, /bez sterowania Deye/);
  assert.match(html, /Nie sumujemy ich ponownie/);
});

test("unknown import is never represented as 0 kW or a full progress bar", () => {
  const card = make({soc: 10, grid_import: "unknown", grid_status: "blokada"});
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /⚠ Grid Guard: blokada/);
  assert.match(html, /— \/ — kW/);
  assert.match(html, /class="fill gridfill" style="width:0%"/);
});

test("updating entity values changes live card without generating YAML", () => {
  const card = make({soc: 10, grid_limit: 15, grid_import: 1});
  const first = card.shadowRoot.innerHTML;
  const later = { ...stateMap({soc: 75, grid_limit: 20, grid_import: 3}) };
  card.hass = {states:later};
  const next = card.shadowRoot.innerHTML;
  assert.notEqual(next, first);
  assert.match(next, /75%/);
  assert.match(next, /20 kW/);
});
