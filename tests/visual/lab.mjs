import assert from "node:assert/strict";
import fs from "node:fs";
import {chromium} from "playwright";

const browser=await chromium.launch({headless:true});
const formats=[
 {name:"deye-lab-desktop",width:1440,dark:false},
 {name:"deye-lab-mobile",width:390,dark:false},
 {name:"deye-lab-mobile-dark",width:390,dark:true}
];
fs.mkdirSync("visual-artifacts",{recursive:true});
for(const fmt of formats){
 const page=await browser.newPage({viewport:{width:fmt.width,height:980},deviceScaleFactor:1});
 const css=fmt.dark?
 "--primary-text-color:#e9f3fa;--secondary-text-color:#b5c6cf;--ha-card-background:#22313b;--secondary-background-color:#2f4149;--divider-color:#45616b;background:#14222a;color:#e9f3fa":
 "--primary-text-color:#1c3038;--secondary-text-color:#5d6f7b;--ha-card-background:#fff;--secondary-background-color:#f4f7f8;--divider-color:#e3e9ef;background:#f4f6f7;color:#1c3038";
 await page.setContent('<html><head><meta name="viewport" content="width=device-width,initial-scale=1">'+
  '<style>html,body{margin:0}body{font-family:Arial,sans-serif;'+css+'}ha-icon{display:inline-block;width:18px;height:18px}</style></head><body></body></html>');
 await page.addScriptTag({path:"custom_components/estadi_energy_pilot/lab_card.js"});
 await page.evaluate(()=>{
   const card=document.createElement("estadi-energy-lab-card");
   card.setConfig({result_entity:"sensor.lab",tests:[
    {key:"meters",entity_id:"button.lab_meters"},
    {key:"polarity",entity_id:"button.lab_polarity"},
    {key:"limits",entity_id:"button.lab_limits"},
    {key:"forecast",entity_id:"button.lab_forecast"},
    {key:"tou",entity_id:"button.lab_tou"},
    {key:"write_capability",entity_id:"button.lab_write"},
    {key:"preflight",entity_id:"button.lab_preflight"}
   ]});
   document.body.appendChild(card);
   const candidates=Array.from({length:15},(_,i)=>({
    entity:"number.deye_tou_program_"+(i+1)+"_charge_power",
    label:"DEYE Time of Use "+(i+1)+" Charge Power",
    state:"5000",domain:"number",min:0,max:10000,step:100,unit:"W",
    detected_by:i%2?"same_deye_device":"name_match"
   }));
   card.hass={states:{"sensor.lab":{
     state:"blokada",last_updated:"2026-11-07T10:39:00+01:00",
     attributes:{ostatni_test:"2026-11-07T10:39:00+01:00",
       szczegoly:{test:"write_capability",status:"blokada",
         checked_at:"2026-11-07T10:39:00+01:00",
         reason:"To wykaz kandydatów, nie potwierdzenie możliwości sterowania.",
         discovered:15,same_deye_device_count:7,candidates}}}},
     callService:async()=>{}
   };
 });
 const geometry=await page.evaluate(()=>{
  const root=document.querySelector("estadi-energy-lab-card").shadowRoot;
  const scroll=root.querySelector(".tablewrap");
  return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,
   buttons:root.querySelectorAll("button[data-test]").length,
   rows:root.querySelectorAll("tbody tr").length,
   copyButton:!!root.querySelector("[data-copy]"),
   tableContentWidth:scroll.scrollWidth,tableViewportWidth:scroll.clientWidth};
 });
 console.log(fmt.name,JSON.stringify(geometry));
 assert.equal(geometry.buttons,7);
 assert.equal(geometry.rows,15);
 assert.ok(geometry.copyButton);
 assert.ok(geometry.documentWidth<=geometry.viewport+2,"full page overflow");
 await page.screenshot({path:"visual-artifacts/"+fmt.name+".png",fullPage:true});
 await page.close();
}
await browser.close();
