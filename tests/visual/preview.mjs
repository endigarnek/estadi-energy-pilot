import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {chromium} from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const output = path.join(root, "visual-artifacts");
fs.mkdirSync(output, {recursive: true});
const cardPath = path.join(root, "custom_components/estadi_energy_pilot/overview_card.js");
const browser = await chromium.launch({headless: true});
const keys = ["soc","pv","home","ev","pump","grid_import","grid_limit","grid_headroom",
  "grid_status","health_status","tariff_zone","next_cheap","smart_charge_power","smart_charge_target"];
const scenarios = [
  {name:"desktop-warning", width:1440, height:1050, dark:false, values:{
    soc:10,pv:0,home:1532,ev:320,pump:846,grid_import:"unknown",grid_limit:15,
    grid_headroom:"unknown",grid_status:"blokada",health_status:"Działa",
    tariff_zone:"cheap",next_cheap:"2026-11-06T23:00:00+01:00",smart_charge_power:"unknown",
    smart_charge_target:"unknown"
  }},
  {name:"desktop-healthy", width:1440, height:1050, dark:false, values:{
    soc:78,pv:5600,home:3200,ev:900,pump:720,grid_import:1.6,grid_limit:15,
    grid_headroom:13.4,grid_status:"ok",health_status:"Działa",
    tariff_zone:"peak",next_cheap:"2026-11-06T23:00:00+01:00",smart_charge_power:4,
    smart_charge_target:85
  }},
  {name:"mobile-warning", width:390, height:920, dark:false, values:{
    soc:10,pv:0,home:1532,ev:320,pump:846,grid_import:"unknown",grid_limit:15,
    grid_headroom:"unknown",grid_status:"blokada",health_status:"Działa",
    tariff_zone:"cheap",next_cheap:"2026-11-06T23:00:00+01:00",smart_charge_power:"unknown",
    smart_charge_target:"unknown"
  }},
  {name:"mobile-dark", width:390, height:920, dark:true, values:{
    soc:78,pv:5600,home:3200,ev:900,pump:720,grid_import:1.6,grid_limit:15,
    grid_headroom:13.4,grid_status:"ok",health_status:"Działa",
    tariff_zone:"peak",next_cheap:"2026-11-06T23:00:00+01:00",smart_charge_power:4,
    smart_charge_target:85
  }},
];
for (const scenario of scenarios) {
  const page = await browser.newPage({viewport:{width:scenario.width,height:scenario.height},
    deviceScaleFactor:1});
  page.on("pageerror", (e) => {throw e;});
  const darkCSS = scenario.dark ?
    "--primary-text-color:#edf2fa;--secondary-text-color:#b3c0d2;--card-background-color:#222933;--ha-card-background:#222933;--secondary-background-color:#303946;--divider-color:#404b59;background:#101820;color:#eef1f6" :
    "--primary-text-color:#182332;--secondary-text-color:#5b6575;--card-background-color:#fff;--ha-card-background:#fff;--secondary-background-color:#f4f6f9;--divider-color:#e4eaf0;background:#f5f7f9;color:#162032";
  await page.setContent('<html lang="pl"><head><meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<style>html,body{margin:0;padding:0}body{font-family:Arial,sans-serif;' + darkCSS + '}' +
    'ha-icon{display:inline-flex;width:20px;height:20px;border-radius:6px;background:currentColor;opacity:.65}</style>' +
    '</head><body></body></html>');
  await page.addScriptTag({path:cardPath});
  await page.evaluate(({keys,values}) => {
    const card=document.createElement("estadi-energy-overview-card");
    card.setConfig(Object.fromEntries(keys.map(k=>["entity_"+k,"sensor."+k])));
    document.body.appendChild(card);
    const states=Object.fromEntries(Object.entries(values).map(([k,v])=>[
      "sensor."+k, {state:String(v),last_updated:new Date().toISOString(),
      attributes:k==="health_status"?{wiek_odswiezenia_s:20,przyczyna:"Wszystkie odczyty dostępne"}:{}}
    ]));
    card.hass={states};
  },{keys,values:scenario.values});
  await page.screenshot({path:path.join(output,scenario.name+".png"),fullPage:true});
  const dimensions=await page.evaluate(()=>{
    const card=document.querySelector("estadi-energy-overview-card");
    const grid=card.shadowRoot.querySelector(".metrics");
    return {pageWidth:document.documentElement.scrollWidth, viewportWidth:innerWidth,
      cardWidth:card.getBoundingClientRect().width, metricCount:grid.children.length,
      heading:card.shadowRoot.querySelector("h1")?.textContent};
  });
  console.log(scenario.name,JSON.stringify(dimensions));
  assert.equal(dimensions.metricCount,4,"four core indicators must remain visible");
  assert.ok(dimensions.pageWidth <= dimensions.viewportWidth+1,
    "no horizontal page overflow at "+scenario.width+"px");
  assert.ok(dimensions.cardWidth>300);
  await page.close();
}
await browser.close();
console.log("All responsive screenshot smoke checks passed.");
