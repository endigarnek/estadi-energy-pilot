import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
const src=fs.readFileSync("custom_components/estadi_energy_pilot/lab_card.js","utf8");
const defs=new Map();
const sandbox={
 HTMLElement:class {
  attachShadow(){
   this.shadowRoot={innerHTML:"",querySelectorAll:()=>[],querySelector:()=>null};
   return this.shadowRoot;
  }
 },
 customElements:{get:key=>defs.get(key),define:(key,v)=>defs.set(key,v)},
 window:{customCards:[]},
};
vm.runInNewContext(src,sandbox);
const Lab=defs.get("estadi-energy-lab-card");
function make(testResult){
 const card=new Lab();
 card.setConfig({result_entity:"sensor.lab",tests:[
  {key:"meters",entity_id:"button.lab_meters"},
  {key:"write_capability",entity_id:"button.lab_write_capability"},
  {key:"write_capability_more",entity_id:"button.lab_write_capability_more"},
  {key:"charge_limits",entity_id:"button.lab_charge_limits"},
  {key:"preflight",entity_id:"button.lab_preflight"}
 ]});
 card.hass={states:{"sensor.lab":{
  state:testResult.status||"blokada",last_updated:"2026-11-07T10:01:00+01:00",
  attributes:{szczegoly:testResult,ostatni_test:"2026-11-07T10:01:00+01:00"}
 }},callService:async()=>{}};
 return card;
}
test("Deye candidates display readable metadata and copy complete inventory",()=>{
 const card=make({test:"write_capability",status:"blokada",
  discovered:2,same_deye_device_count:1,checked_at:"2026-11-07",
  reason:"To tylko odczyt",candidates:[
   {entity:"number.program_1_power",label:"Deye TOU power",
    state:"5000",domain:"number",unit:"W",min:0,max:10000,step:100,
    detected_by:"same_deye_device",options:[]},
   {entity:"switch.deye_grid_charge",label:"Grid charging",
    state:"off",detected_by:"name_match",options:[]}
  ]});
 const html=card.shadowRoot.innerHTML;
 for(const text of ["Laboratorium Deye","2 wszystkich",
  "number.program_1_power","Deye TOU power","5000","0–10000 co 100",
  "To samo urządzenie","Kopiuj wykaz encji","Tylko odczyt"]){
  assert.ok(html.includes(text),text);
 }
 const copy=card.copyPayload();
 assert.match(copy,/number.program_1_power/);
 assert.match(copy,/Wysłane polecenia do Deye: NIE/);
 assert.match(copy,/min=0/);
});
test("second regulator page is copyable and clearly numbered",()=>{
 const card=make({test:"write_capability_more",status:"blokada",
  page:2,pages:2,discovered:78,shown:38,remaining:0,candidates:[
    {entity:"switch.deye_grid_charge",label:"Deye Grid Charge",
     domain:"switch",state:"off",detected_by:"same_deye_device"}
  ]});
 assert.match(card.shadowRoot.innerHTML,/strona 2 \/ 2/);
 assert.match(card.copyPayload(),/Strona: 2 \/ 2/);
 assert.match(card.copyPayload(),/switch.deye_grid_charge/);
});
test("editable current must not be described as a physical BMS limit",()=>{
 const card=make({test:"charge_limits",status:"informacja",
  settings:{grid_charge_current:{value:40,unit:"A",min_ui:0,max_ui:350,step_ui:1},
   max_charge_current:{value:200,unit:"A"},
   max_grid_import:{value:31000,unit:"W"},
   peak_shaving:{value:8000,unit:"W"}},
  approximate_dc_charge_kw_at_current_setting:1.92,
  contracted_connection_kw:15,inverter_setting_above_connection_limit:true});
 const html=card.shadowRoot.innerHTML;
 assert.match(html,/40 A/);
 assert.match(html,/Konfigurowalne/);
 assert.match(html,/15 kW/);
 assert.match(html,/1.92 kW/);
 assert.match(html,/nie są fizycznymi limitami BMS/);
 assert.match(card.copyPayload(),/grid_charge_current/);
});
test("only configured diagnostic button can be pressed",async()=>{
 const card=make({test:"meters",status:"ok",reason:"Odczyt gotowy"});
 let calls=[];
 card._hass.callService=async(...args)=>{calls.push(args);};
 await card.trigger("meters");
 assert.equal(calls.length,1);
 assert.equal(calls[0][0],"button");
 assert.equal(calls[0][1],"press");
 assert.equal(calls[0][2].entity_id,"button.lab_meters");
 await card.trigger("unknown_test");
 assert.equal(calls.length,1);
});
test("preflight displays real blockers, not false-ready state",()=>{
 const card=make({test:"preflight",status:"blokada",
  blockers:["Brak BMS","Nieznany odczyt zwrotny"]});
 const html=card.shadowRoot.innerHTML;
 assert.match(html,/Sterowanie Deye pozostaje wyłączone/);
 assert.match(html,/Brak BMS/);
 assert.match(html,/Nieznany odczyt zwrotny/);
});
test("unsafe HA text is escaped in DOM",()=>{
 const card=make({test:"write_capability",status:"blokada",candidates:[
  {entity:"number.deye_program",label:'<img src=x onerror="evil()">',
   state:"5",detected_by:"name_match"}
 ]});
 const html=card.shadowRoot.innerHTML;
 assert.doesNotMatch(html,/<img/);
 assert.match(html,/&lt;img/);
});
test("read-only UI contains no physical write endpoints",()=>{
 for(const needle of [
   "number.set_value","switch.turn_on","select.select_option",
   'callService("number"','callService("switch"','callService("select"',
   "fetch(","XMLHttpRequest"
 ]){
  assert.equal(src.includes(needle),false,needle);
 }
});
