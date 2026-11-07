import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
const src=fs.readFileSync("custom_components/estadi_energy_pilot/plan_card.js","utf8");
const classes=new Map();
const sandbox={
 HTMLElement:class{
  attachShadow(){this.shadowRoot={innerHTML:"",querySelectorAll:()=>[]};return this.shadowRoot;}
 },
 customElements:{get:id=>classes.get(id),define:(id,c)=>classes.set(id,c)},
 window:{customCards:[]},
};
vm.runInNewContext(src,sandbox);
const Card=classes.get("estadi-energy-plan-card");
const make=(state,rows,attrs={})=>{
 const card=new Card();
 card.setConfig({entity:"sensor.estadi_plan_timeline"});
 card.hass={states:{"sensor.estadi_plan_timeline":{
  state,last_updated:"2026-11-07T12:01:00+01:00",
  attributes:{godziny:rows,planowane_godziny:rows.length,liczba_godzin:rows.length,
   energia_ladowania_z_sieci_kwh:7.8,energia_rozladowania_do_domu_kwh:1.6,
   import_przy_planie_kwh:22,import_bez_dodatkowego_ladowania_kwh:17,...attrs}
 }}};
 return card;
};
const rows=(n=48)=>Array.from({length:n},(_,i)=>({
 czas:"2026-11-"+(i<24?"07":"08")+" "+String(i%24).padStart(2,"0")+":00+0100",
 soc_bazowy_pct:20, soc_plan_pct:40+i/4,
 pv_kwh:0.25,dom_kwh:1.1,import_bazowy_kwh:1.1,import_plan_kwh:1.3,
 ladowanie_siec_kwh:i<5?.8:0,ladowanie_pv_kwh:i===6?.3:0,
 rozladowanie_kwh:i>=10?.2:0,
 moc_ladowania_siec_kw_sr:i<5?.8:0,
 tryb:i<5?"ladowanie_z_sieci":i===6?"ladowanie_z_pv":"rozladowanie",
}));
test("48h card shows real hourly source values and two-day switch",()=>{
 const html=make("gotowy",rows()).shadowRoot.innerHTML;
 for(const phrase of ["Godzinowy harmonogram magazynu","SOC plan","SOC bez planu",
  "Ładowanie z sieci","7,8 kWh","22 kWh","17 kWh","2026-11-07","2026-11-08"]) {
  assert.ok(html.includes(phrase),phrase);
 }
 assert.match(html,/Godzina/);
 assert.match(html,/rect/);
 assert.match(html,/aria-pressed="true"/);
});
test("incomplete forecast never claims complete 48h plan or a sum",()=>{
 const html=make("niepelna_prognoza",rows(2),{
  planowane_godziny:2,
  przyczyna:"Brak prognozy PV na dalszy dzień"
 }).shadowRoot.innerHTML;
 assert.match(html,/Niepełna prognoza/);
 assert.doesNotMatch(html,/7,8 kWh/);
 assert.match(html,/Brak prognozy PV/);
});
test("no plan cannot fake grid charging",()=>{
 const data=rows(48).map(r=>({...r,tryb:"brak_planu",
  soc_plan_pct:null,ladowanie_siec_kwh:null,moc_ladowania_siec_kw_sr:null}));
 const html=make("brak_planu",data,{planowane_godziny:0}).shadowRoot.innerHTML;
 assert.match(html,/Brak wariantu ładowania/);
 assert.doesNotMatch(html,/7,8 kWh/);
});
test("text is escaped, scripts cannot be injected through HA attributes",()=>{
 const html=make("gotowy",rows(48),{przyczyna:'<img onerror="boom()">'})
  .shadowRoot.innerHTML;
 assert.doesNotMatch(html,/<img/);
 assert.match(html,/&lt;img/);
});
test("plan widget has no HA write calls",()=>{
 for(const needle of ["hass.callService","hass.services","fetch(","XMLHttpRequest",
  "number.set_value","switch.turn_on","select.select_option"]) {
  assert.equal(src.includes(needle),false,needle);
 }
});
