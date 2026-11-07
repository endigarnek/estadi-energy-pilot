import assert from "node:assert/strict";
import fs from "node:fs";
import {chromium} from "playwright";
import * as mdi from "@mdi/js";
const browser=await chromium.launch({headless:true});
const keys=["soc","pv","home","battery_power","losses","ev","pump","grid_import","grid_raw",
"grid_limit","grid_headroom","grid_status","smart_charge_status","smart_charge_start","smart_charge_finish",
"smart_charge_power","smart_charge_target","smart_charge_energy","sim_status","sim_hours",
"sim_pv_kwh","sim_grid_kwh","sim_soc_end","next_cheap","history_status"];
const paths={
 "mdi:solar-power":mdi.mdiSolarPower,
 "mdi:transmission-tower":mdi.mdiTransmissionTower,
 "mdi:home-lightning-bolt-outline":mdi.mdiHomeLightningBoltOutline,
 "mdi:heat-wave":mdi.mdiWavesArrowUp,
 "mdi:battery-medium":mdi.mdiBatteryMedium,
 "mdi:power-plug":mdi.mdiPowerPlug,
};
const scenario=[
 {id:"compact-desktop",w:1440,dark:false},
 {id:"compact-mobile",w:390,dark:false},
 {id:"compact-mobile-dark",w:390,dark:true}
];
fs.mkdirSync("visual-artifacts",{recursive:true});
for(const sc of scenario){
 const page=await browser.newPage({viewport:{width:sc.w,height:950},deviceScaleFactor:1});
 const colors=sc.dark ?
 "--primary-text-color:#eef4f9;--secondary-text-color:#b8c4d1;--ha-card-background:#212b34;--secondary-background-color:#2c3943;--divider-color:#43515d;background:#111b23;color:#eef4f9":
 "--primary-text-color:#182d33;--secondary-text-color:#596c78;--ha-card-background:#fff;--secondary-background-color:#f4f6f8;--divider-color:#e4eaf0;background:#f4f6f8;color:#162b32";
 await page.setContent('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+
 'html,body{margin:0}body{font-family:Arial,sans-serif;'+colors+'}</style></head><body></body></html>');
 await page.evaluate((icons)=>{
   class Icon extends HTMLElement{
     connectedCallback(){
       const d=icons[this.getAttribute("icon")];
       if(d)this.innerHTML='<svg width="21" height="21" viewBox="0 0 24 24" fill="currentColor"><path d="'+d+'"/></svg>';
     }
   }
   customElements.define("ha-icon",Icon);
 },paths);
 await page.addScriptTag({path:"custom_components/estadi_energy_pilot/control_card.js"});
 await page.evaluate((keys)=>{
   const card=document.createElement("estadi-energy-control-card");
   card.setConfig(Object.fromEntries(keys.map(k=>["entity_"+k,"sensor."+k])));
   document.body.appendChild(card);
   const sample={
    soc:10,pv:0,home:1684,battery_power:13,losses:92,ev:320,pump:846,
    grid_raw:1.764,grid_import:"unknown",grid_limit:15,grid_headroom:"unknown",
    grid_status:"blokada",smart_charge_status:"brak_celu",sim_status:"niepelna_prognoza_pv",
    sim_hours:2.75,sim_pv_kwh:0,sim_grid_kwh:1.6,sim_soc_end:10,
   };
   const states=Object.fromEntries(Object.entries(sample).map(([k,v])=>["sensor."+k,
    {state:String(v),last_updated:"2026-11-07T00:40:00Z",attributes:{}}]));
   states["sensor.sim_status"].attributes={
      przyczyna:"Brak godzinowej prognozy PV od 07.11 04:00",
      harmonogram_48h:[{soc_do:10},{soc_do:10},{soc_do:10}],
   };
   card.hass={states};
 },keys);
 const dims=await page.evaluate(()=>{
   const host=document.querySelector("estadi-energy-control-card");
   const root=host.shadowRoot,flow=root.querySelector(".flow");
   return {viewport:innerWidth,pageWidth:document.documentElement.scrollWidth,
     hostWidth:host.getBoundingClientRect().width,hostHeight:host.getBoundingClientRect().height,
     flowWidth:flow.getBoundingClientRect().width,flowScroll:flow.scrollWidth,
     panelCount:root.querySelectorAll(".card").length};
 });
 console.log(sc.id,JSON.stringify(dims));
 assert.equal(dims.panelCount,4);
 assert.ok(dims.pageWidth<=dims.viewport+2,"horizontal page overflow");
 assert.ok(dims.flowScroll<=dims.flowWidth+2,"flow card overflow");
 if(sc.w>=1000)assert.ok(dims.hostHeight<750,"desktop should be compact");
 await page.screenshot({path:"visual-artifacts/"+sc.id+".png",fullPage:true});
 await page.close();
}
await browser.close();
console.log("Compact panel screenshots and overflow checks completed");
