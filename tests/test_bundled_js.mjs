import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const root="custom_components/estadi_energy_pilot/";
const names=[
 "forecast_card.js","overview_card.js","control_card.js",
 "details_card.js","plan_card.js","lab_card.js"
];
const merged=names.map(name=>fs.readFileSync(root+name,"utf8")).join("\n");
const tags=[
 "estadi-energy-forecast-card","estadi-energy-overview-card",
 "estadi-energy-control-card","estadi-energy-details-card",
 "estadi-energy-plan-card","estadi-energy-lab-card"
];

test("complete installed JS bundle is syntactically valid, not just individual source files",()=>{
 assert.doesNotThrow(()=>new vm.Script(merged));
});

test("entire bundle registers every custom card on a fresh HA page",()=>{
 const cards=new Map();
 const window={customCards:[]};
 vm.runInNewContext(merged,{
  customElements:{
   get(tag){return cards.get(tag);},
   define(tag,ctor){if(cards.has(tag))throw new Error("Duplicate tag "+tag);cards.set(tag,ctor);}
  },
  window,HTMLElement:class HTMLElement{},
 });
 for(const tag of tags)assert.ok(cards.has(tag),"Missing "+tag);
 assert.equal(window.customCards.filter(x=>tags.includes(x.type)).length,6);
});

test("reload of entire bundle is safe when HA already has its custom cards",()=>{
 const cards=new Map(),window={customCards:[]};
 const context={
  customElements:{get:tag=>cards.get(tag),define:(tag,ctor)=>cards.set(tag,ctor)},
  window,HTMLElement:class HTMLElement{},
 };
 vm.runInNewContext(merged,context);
 vm.runInNewContext(merged,context);
 assert.equal(cards.size,6);
 assert.equal(window.customCards.filter(x=>tags.includes(x.type)).length,6);
});
