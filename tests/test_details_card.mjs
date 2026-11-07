import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
const src=fs.readFileSync("custom_components/estadi_energy_pilot/details_card.js","utf8");
const classes=new Map();
const sandbox={
 HTMLElement:class{attachShadow(){this.shadowRoot={innerHTML:""};return this.shadowRoot;}},
 customElements:{get:id=>classes.get(id),define:(id,c)=>classes.set(id,c)},
 window:{customCards:[]},
};
vm.runInNewContext(src,sandbox);
const Card=classes.get("estadi-energy-details-card");
const make=(value,unit)=>{
 const card=new Card();
 card.setConfig({title:"Stan magazynu",items:[
   {label:"Moc z sieci",entity:"sensor.grid"},
   {label:"Stan",entity:"sensor.status"},
   {label:"Brak",entity:"sensor.missing"},
 ]});
 card.hass={states:{
  "sensor.grid":{state:String(value),last_updated:"2026-11-07",attributes:{unit_of_measurement:unit}},
  "sensor.status":{state:"niepelna_prognoza",last_updated:"2026-11-07",attributes:{}},
 }};
 return card;
};
test("compact details show correct unit and readable status labels",()=>{
 const html=make(1764,"W").shadowRoot.innerHTML;
 assert.match(html,/Moc z sieci/);
 assert.match(html,/1.?764/);
 assert.match(html,/>W<\/small>/);
 assert.match(html,/niepelna prognoza/);
 assert.match(html,/Encja nie jest dostępna/);
 assert.doesNotMatch(html,/overflow:hidden;text-overflow:ellipsis;white-space:nowrap/);
});
test("unavailable does not appear as valid zero and malicious state escaped",()=>{
 const html=make("unavailable",'<img src=x onerror="evil()">').shadowRoot.innerHTML;
 assert.match(html,/Brak aktualnego wyniku/);
 assert.doesNotMatch(html,/<img/);
});
test("card sends no commands",()=>{
 for(const unsafe of ["hass.callService","number.set_value","fetch(","XMLHttpRequest","select.select_option"]){
  assert.equal(src.includes(unsafe),false,unsafe);
 }
});
