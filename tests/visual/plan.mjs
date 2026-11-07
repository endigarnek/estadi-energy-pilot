import assert from "node:assert/strict";
import fs from "node:fs";
import { chromium } from "playwright";
const browser=await chromium.launch({headless:true});
const scenarios=[
 {id:"hourly-plan-desktop",width:1440,dark:false},
 {id:"hourly-plan-mobile",width:390,dark:false},
 {id:"hourly-plan-mobile-dark",width:390,dark:true}
];
fs.mkdirSync("visual-artifacts",{recursive:true});
for(const sc of scenarios){
 const page=await browser.newPage({viewport:{width:sc.width,height:900},deviceScaleFactor:1});
 const colors=sc.dark?
 "--primary-text-color:#eef4f9;--secondary-text-color:#b7c5d1;--ha-card-background:#232e38;--secondary-background-color:#303e49;--divider-color:#465563;background:#14202a;color:#edf4fc":
 "--primary-text-color:#172c33;--secondary-text-color:#617480;--ha-card-background:#fff;--secondary-background-color:#f4f6f8;--divider-color:#e4e9ed;background:#f4f6f8;color:#172c33";
 await page.setContent('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0}body{font-family:Arial,sans-serif;'+colors+'}</style></head><body></body></html>');
 await page.addScriptTag({path:"custom_components/estadi_energy_pilot/plan_card.js"});
 await page.evaluate(()=>{
  const card=document.createElement("estadi-energy-plan-card");
  card.setConfig({entity:"sensor.energy_plan_timeline"});
  document.body.appendChild(card);
  const rows=Array.from({length:48},(_,i)=>({
   czas:"2026-11-"+(i<24?"07":"08")+" "+String(i%24).padStart(2,"0")+":00+0100",
   soc_bazowy_pct:10,soc_plan_pct:10+Math.min(i,11)*5,
   moc_ladowania_siec_kw_sr:i<8?5:0,ladowanie_siec_kwh:i<8?5:0,
   ladowanie_pv_kwh:i>=8&&i<15?1.5:0,rozladowanie_kwh:i>18?.8:0,
   import_plan_kwh:2.1,import_bazowy_kwh:1.2,
   tryb:i<8?"ladowanie_z_sieci":i>18?"rozladowanie":"spoczynek"
  }));
  card.hass={states:{"sensor.energy_plan_timeline":{
    state:"gotowy",last_updated:"2026-11-07T11:21:00+01:00",
    attributes:{godziny:rows,liczba_godzin:48,planowane_godziny:48,
      energia_ladowania_z_sieci_kwh:12.5,energia_rozladowania_do_domu_kwh:5.2,
      import_przy_planie_kwh:18.8,import_bez_dodatkowego_ladowania_kwh:9.6,
      przyczyna:"Plan ma charakter doradczy — bez sterowania Deye"}}}};
 });
 const dims=await page.evaluate(()=>{
  const el=document.querySelector("estadi-energy-plan-card");
  const content=el.shadowRoot.querySelector(".table-wrap");
  return {viewportWidth:innerWidth,pageWidth:document.documentElement.scrollWidth,
    cardWidth:el.getBoundingClientRect().width,chartCount:el.shadowRoot.querySelectorAll("svg").length,
    tables:el.shadowRoot.querySelectorAll("table").length,scrollWidth:content.scrollWidth,
    clientWidth:content.clientWidth};
 });
 assert.ok(dims.pageWidth <= dims.viewportWidth+2,"horizontal page overflow");
 assert.equal(dims.chartCount,1);
 assert.equal(dims.tables,1);
 console.log(sc.id,JSON.stringify(dims));
 await page.screenshot({path:"visual-artifacts/"+sc.id+".png",fullPage:true});
 await page.close();
}
await browser.close();
