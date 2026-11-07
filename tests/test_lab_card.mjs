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
    state:"5000",unit:"W",min:0,max:10000,step:100,
    detected_by:"same_deye_device",options:[]},
   {entity:"switch.deye_grid_charge",label:"Grid charging",
    state:"off",detected_by:"name_match",options:[]}
  ]});
 const html=card.shadowRoot.innerHTML;
 for(const text of ["Laboratorium Deye","2 potencjalnych regulatorów",
  "number.program_1_power","Deye TOU power","5000","0–10000 co 100",
  "To samo urządzenie","Kopiuj wykaz encji","Tylko odczyt"]){
  assert.ok(html.includes(text),text);
 }
 const copy=card.copyPayload();
 assert.match(copy,/number.program_1_power/);
 assert.match(copy,/Wysłane polecenia do Deye: NIE/);
 assert.match(copy,/min=0/);
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
