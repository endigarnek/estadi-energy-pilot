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
    grid_status: "ok", health_status: "Działa", tariff_zone: "cheap",
  });
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /5 kW/);
  assert.match(html, /1,53/);
  assert.match(html, /15 kW/);
  assert.match(html, /Sterowanie Deye: wyłączone/);
  assert.match(html, /EV i pompa są już w Deye Load/);
  assert.match(html, /Bilans chwilowy/);
  assert.match(html, /gauge/);
});

test("unknown import is never represented as 0 kW or a full progress bar", () => {
  const card = make({soc: 10, grid_import: "unknown", grid_status: "blokada"});
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /Grid Guard wymaga weryfikacji/);
  assert.match(html, /Grid Guard: blokada/);
  assert.match(html, /— \/ —/);
  assert.match(html, /class="progress grid-progress [^"]*"[^>]*><i style="width:0%"/);
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

test("a failure state is not falsely marked healthy", () => {
  const card = make({health_status: "Nie działa", grid_status: "brak kalibracji"});
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /System: Nie działa/);
  assert.match(html, /status warning/);
  assert.doesNotMatch(html, /Odczyty aktywne/);
});

test("PV zero is valid at night, while an unknown SOC is not zero percent", () => {
  const card = make({pv: 0, home: 1532, soc: "unavailable"});
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /0 W/);
  assert.match(html, /Magazyn SOC/);
  assert.match(html, /Stan magazynu: —/);
  assert.doesNotMatch(html, /Stan magazynu: 0%/);
});

test("escapes untrusted grid text and never renders HTML from sensor states", () => {
  const card = make({grid_status: '<img src=x onerror="evil()">', health_status: "Błąd"});
  assert.doesNotMatch(card.shadowRoot.innerHTML, /<img/);
  assert.match(card.shadowRoot.innerHTML, /&lt;img/);
});

test("no write actions or external requests in main card", () => {
  const source = fs.readFileSync(filepath, "utf-8");
  for (const forbidden of ["hass.callService", "number.set_value", "switch.turn_on", "fetch(", "XMLHttpRequest"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});

test("compact widget fits one card and preserves safe unknown states", () => {
  const item = new Card();
  item.setConfig({
    mode: "compact", entity_pv: "sensor.pv", entity_home: "sensor.home",
    entity_soc: "sensor.soc", entity_grid_import: "sensor.grid_import",
    entity_grid_status: "sensor.grid_status", entity_health_status: "sensor.health_status",
  });
  item.hass = {states:stateMap({
    pv: 0, home: 1500, soc: 10, grid_import: "unknown",
    grid_status: "brak kalibracji", health_status: "Działa",
  })};
  const markup = item.shadowRoot.innerHTML;
  assert.match(markup, /Energia w skrócie/);
  assert.match(markup, /1,5/);
  assert.match(markup, /⚠ Wymaga uwagi/);
  assert.match(markup, /Brak odczytu nie oznacza 0 kW/);
  assert.doesNotMatch(markup, /Bilans chwilowy/);
});

test("breakdown does not invent a plausible split when EV plus pump exceed Deye Load", () => {
  const item = make({
    pv: 500, home: 1000, ev: 900, pump: 800,
    grid_status: "ok", health_status: "Działa", grid_import: 1, grid_limit: 15,
  });
  const html = item.shadowRoot.innerHTML;
  assert.match(html, /Odczyty EV i pompy przekraczają Deye Load/);
  assert.doesNotMatch(html, /class="usage" aria-label=/);
});

test("stale health probe is never presented as a healthy system", () => {
  const item = make({
    pv: 800, home: 1000, soc: 30,
    grid_status: "ok", health_status: "Działa", grid_import: 1, grid_limit: 15,
  });
  const states = stateMap({
    pv: 800, home: 1000, soc: 30,
    grid_status: "ok", grid_import: 1, grid_limit: 15,
  });
  states["sensor.health_status"] = {
    state: "Działa", last_updated: "2026-11-06T23:00:00+01:00",
    attributes: {wiek_odswiezenia_s: 4000, przyczyna: "Odświeżanie zatrzymane"},
  };
  item.hass = {states};
  assert.match(item.shadowRoot.innerHTML, /Odczyty mogą być nieaktualne/);
  assert.match(item.shadowRoot.innerHTML, /Odświeżanie zatrzymane/);
  assert.match(item.shadowRoot.innerHTML, /status warning/);
});

test("warns at 90 percent of the configured connection capacity", () => {
  const near = make({
    health_status:"Działa", grid_status:"ok", grid_import:14, grid_limit:15,
  });
  assert.match(near.shadowRoot.innerHTML, /Blisko limitu przyłącza/);
  assert.match(near.shadowRoot.innerHTML, /grid-progress near/);

  const exceeded = make({
    health_status:"Działa", grid_status:"ok", grid_import:16, grid_limit:15,
  });
  assert.match(exceeded.shadowRoot.innerHTML, /Przekroczono limit przyłącza/);
  assert.match(exceeded.shadowRoot.innerHTML, /grid-progress over/);
});
