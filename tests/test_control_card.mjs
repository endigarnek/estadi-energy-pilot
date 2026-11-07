import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
const src=fs.readFileSync("custom_components/estadi_energy_pilot/control_card.js","utf8");
const items=new Map();
const sandbox={
 HTMLElement:class{attachShadow(){this.shadowRoot={innerHTML:""};return this.shadowRoot;}},
 customElements:{get:k=>items.get(k),define:(k,v)=>items.set(k,v)},
 window:{customCards:[]},
};
vm.runInNewContext(src,sandbox);
const Card=items.get("estadi-energy-control-card");
const keys=["soc","pv","home","battery_power","losses","ev","pump","grid_import","grid_raw","grid_limit",
 "grid_headroom","grid_status","smart_charge_status","smart_charge_start","smart_charge_finish",
 "smart_charge_power","smart_charge_target","smart_charge_energy","sim_status","sim_hours",
 "sim_pv_kwh","sim_grid_kwh","sim_soc_end","next_cheap","history_status"];
const build=(values,attr={})=>{
 const item=new Card();
 item.setConfig(Object.fromEntries(keys.map(k=>["entity_"+k,"sensor."+k])));
 const states=Object.fromEntries(Object.entries(values).map(([k,v])=>["sensor."+k,
  {state:String(v),last_updated:"2026-11-07T01:00:00+01:00",attributes:attr[k]||{}}]));
 item.hass={states};
 return item;
};
test("compact power flow includes losses, PV, home and battery without massive hero",()=>{
 const item=build({soc:10,pv:0,home:1684,battery_power:13,losses:92,
   grid_raw:1.764,grid_import:"unknown",grid_limit:15,ev:320,pump:846,
   sim_hours:2.5,sim_pv_kwh:0,sim_grid_kwh:1.4});
 const html=item.shadowRoot.innerHTML;
 for(const text of ["Centrum energii","92 W","1,76 kW","1,68 kW","10%","0 W","EV","Pompa"])assert.ok(html.includes(text),text);
 assert.match(html,/nie import/);
 assert.match(html,/Sterowanie Deye: WYŁĄCZONE/);
 assert.doesNotMatch(html,/<h1>Energia w Twoim domu/);
 assert.doesNotMatch(html,/1,4 kWh/); // incomplete horizon never shown as 48h total
});
test("full 48h plan shows actual advisory hours, power and grid charge",()=>{
 const item=build({
   soc:25,pv:2300,home:1000,grid_import:0.4,sim_hours:48,
   sim_status:"gotowa",sim_pv_kwh:17.6,sim_grid_kwh:8.9,sim_soc_end:70,
   smart_charge_status:"wstepny_plan",smart_charge_power:5,
   smart_charge_energy:8.6,smart_charge_target:75,
   smart_charge_start:"2026-11-08T01:00:00+01:00",
   smart_charge_finish:"2026-11-08T03:00:00+01:00",
 });
 const html=item.shadowRoot.innerHTML;
 for(const text of ["Plan doradczy gotowy","5 kW","8,6 kWh","17,6 kWh","8,9 kWh","75%"])assert.match(html,new RegExp(text));
 assert.doesNotMatch(html,/brak pełnego planu/i);
});
test("missing or malicious sensor states never become invented values nor HTML",()=>{
 const item=build({
   grid_import:"unknown",grid_raw:"unknown",
   smart_charge_status:"brak_celu",sim_status:"niepelna_prognoza_pv",sim_hours:3,
 },{smart_charge_status:{przyczyna:'<img src=x onerror="alert()">'}});
 assert.doesNotMatch(item.shadowRoot.innerHTML,/<img/);
 assert.match(item.shadowRoot.innerHTML,/&lt;img/);
 assert.match(item.shadowRoot.innerHTML,/Brak pełnego planu/);
});
test("no service calls, REST writes or false write-enabled controls",()=>{
 for(const needle of ["hass.callService","number.set_value","select.select_option","switch.turn_on","fetch(","XMLHttpRequest"]) {
   assert.equal(src.includes(needle),false,needle);
 }
});
