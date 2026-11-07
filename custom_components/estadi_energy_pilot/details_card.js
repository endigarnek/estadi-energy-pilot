/* Compact, reusable ESTADI sensor group; values stay live and readable. */
(() => {
"use strict";
const TAG="estadi-energy-details-card";
if(customElements.get(TAG))return;
const esc=(v)=>String(v==null?"":v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const missing=(v)=>v==null||["unknown","unavailable","none","null","nieznany",""].includes(String(v).toLowerCase());
const human=(v)=>String(v).replaceAll("_"," ");
class Details extends HTMLElement {
 constructor(){super();this.attachShadow({mode:"open"});this._cfg={};this._hass=null;this._signature="";}
 setConfig(c){this._cfg=c||{};this._signature="";this.render();}
 static getStubConfig(){return{title:"ESTADI",items:[]};}
 getCardSize(){return 4;}
 getGridOptions(){return{columns:"full",rows:"auto"};}
 set hass(h){
  this._hass=h;if(!h?.states)return;
  const sig=(this._cfg.items||[]).map(x=>{
   const s=h.states[x.entity];return x.entity+":"+(s?s.state+":"+s.last_updated:"missing");
  }).join("|");
  if(sig!==this._signature){this._signature=sig;this.render();}
 }
 render(){
  if(!this.shadowRoot)return;
  const cards=(this._cfg.items||[]).filter(x=>x?.entity).map(x=>{
   const v=this._hass?.states?.[x.entity],raw=v?.state;
   const unit=v?.attributes?.unit_of_measurement;
   const good=!missing(raw);
   const value=good?(Number.isFinite(Number(raw))&&String(raw).trim()!==""
       ?Number(raw).toLocaleString("pl-PL",{maximumFractionDigits:2}) : human(raw)):"—";
   const status=good?unit||"":
      v?"Brak aktualnego wyniku":"Encja nie jest dostępna";
   return '<div class="cell '+(good?"":"missing")+'"><div class="label">'+
       esc(x.label||v?.attributes?.friendly_name||x.entity)+'</div>'+
       '<div class="value">'+esc(value)+(good&&unit?'<small>'+esc(unit)+'</small>':"")+
       '</div>'+(good?'':'<div class="reason">'+esc(status)+'</div>')+'</div>';
  }).join("");
  this.shadowRoot.innerHTML='<style>'+
   ':host{--surface:var(--ha-card-background,var(--card-background-color,#fff));'+
   '--text:var(--primary-text-color,#182b32);--muted:var(--secondary-text-color,#657480);'+
   '--line:var(--divider-color,#e3e9ee);display:block;font:inherit;color:var(--text)}'+
   '*{box-sizing:border-box}ha-card{border:1px solid var(--line);border-radius:15px;'+
   'background:var(--surface);box-shadow:none;padding:14px}h2{margin:0 0 10px;'+
   'font-size:15px;letter-spacing:-.01em}.items{display:grid;'+
   'grid-template-columns:repeat(auto-fit,minmax(min(100%,140px),1fr));gap:7px}'+
   '.cell{background:var(--secondary-background-color,#f5f7f8);border-radius:10px;'+
   'padding:10px;min-width:0}.label{color:var(--muted);font-size:11px;line-height:1.4;'+
   'min-height:30px;overflow-wrap:anywhere}.value{font-size:17px;font-weight:740;'+
   'line-height:1.25;margin-top:6px;overflow-wrap:anywhere;'+
   'font-variant-numeric:tabular-nums}.value small{font-size:10px;font-weight:520;'+
   'color:var(--muted);margin-left:4px}.cell.missing .value{color:var(--muted)}'+
   '.reason{font-size:10px;color:var(--muted);margin-top:4px;line-height:1.4}'+
   '@media(max-width:520px){ha-card{padding:10px;border-radius:12px}'+
   '.items{grid-template-columns:repeat(2,minmax(0,1fr));gap:5px}.cell{padding:8px}}'+
   '</style><ha-card><h2>'+esc(this._cfg.title||"ESTADI")+'</h2>'+
   '<div class="items">'+cards+'</div></ha-card>';
 }
}
customElements.define(TAG,Details);
window.customCards=window.customCards||[];
window.customCards.push({type:TAG,name:"ESTADI — Czytelne wartości",description:"Zwarte metryki z pełnymi etykietami",preview:true});
})();