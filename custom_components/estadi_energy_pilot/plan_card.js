/* ESTADI hourly battery plan. Simulation ONLY; no hardware actions. */
(() => {
"use strict";
const TAG="estadi-energy-plan-card";
if(customElements.get(TAG)) return;
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num=v=>v===null||v===undefined||v===""||/^(unknown|unavailable|none|null|nan)$/i.test(String(v))?
 null:Number.isFinite(Number(v))?Number(v):null;
const nfmt=(n,d=1)=>n===null?"—":n.toLocaleString("pl-PL",{maximumFractionDigits:d});
const txt=(v)=>v==null?"—":String(v).replace(/_/g," ");
const shortTime=t=>String(t||"").slice(11,16);
const dateLabel=t=>String(t||"").slice(0,10);
class EstadiPlan extends HTMLElement{
 constructor(){super();this.attachShadow({mode:"open"});this._cfg={};this._hass=null;this._sig="";this._day=0;}
 static getStubConfig(){return{entity:"sensor.estadi_energy_pilot_plan_48h_harmonogram_godzinowy"};}
 getCardSize(){return this._cfg.compact?4:9;}
 getGridOptions(){return {columns:"full",rows:"auto"};}
 setConfig(v){if(!v?.entity) throw new Error("Podaj encję planu 48h");this._cfg=v;this._sig="";this.render();}
 set hass(v){
  this._hass=v;const s=v?.states?.[this._cfg.entity];
  const signature=!s?"missing":s.state+":"+s.last_updated+
    ":"+(s.attributes?.liczba_godzin??"")+":"+(s.attributes?.planowane_godziny??"");
  if(signature!==this._sig){this._sig=signature;this.render();}
 }
 _chart(rows){
  if(rows.length<2)return'<div class="empty">Brak danych godzinowych do wykresu</div>';
  const W=800, L=33, R=782, dx=(R-L)/rows.length;
  const maxKw=Math.max(1,...rows.flatMap(r=>[
   num(r.moc_ladowania_siec_kw_sr)||0,num(r.rozladowanie_kwh)||0,num(r.ladowanie_pv_kwh)||0]));
  const bar=(k,val,color)=>{
   if(val===null||val<=0)return"";
   const bh=Math.max(1,Math.min(37,val/maxKw*37));
   return '<rect x="'+(L+k*dx+dx*.17).toFixed(2)+'" y="'+(142-bh).toFixed(1)+
     '" width="'+(dx*.22).toFixed(1)+'" height="'+bh.toFixed(1)+
     '" rx="1.6" fill="'+color+'"/>';
  };
  const discharge=(k,v)=>{
   if(v===null||v<=0)return"";
   const height=Math.min(30,v/maxKw*30);
   return'<rect x="'+(L+k*dx+dx*.55).toFixed(2)+'" y="144" width="'+
     (dx*.22).toFixed(1)+'" height="'+height.toFixed(1)+'" rx="1.6" fill="#3b8eb5"/>';
  };
  const line=(field,color,dashed)=>{
   const pieces=[];let pts=[];
   rows.forEach((r,i)=>{
    const v=num(r[field]);
    if(v===null||v<0||v>100){
     if(pts.length>1)pieces.push(pts.join(" "));pts=[];return;
    }
    pts.push((L+(i+.5)*dx).toFixed(1)+","+(88-v*.63).toFixed(1));
   });
   if(pts.length>1)pieces.push(pts.join(" "));
   return pieces.map(p=>'<polyline points="'+p+'" stroke="'+color+
    '" stroke-width="2.6" '+(dashed?'stroke-dasharray="5 4" ':'')+
    'fill="none" stroke-linecap="round" stroke-linejoin="round"/>').join("");
  };
  const bars=rows.map((row,k)=>{
   const chg=num(row.moc_ladowania_siec_kw_sr);
   const pv=num(row.ladowanie_pv_kwh);
   const out=num(row.rozladowanie_kwh);
   return bar(k,chg,"#e5a43c")+bar(k,pv,"#2eae80")+discharge(k,out);
  }).join("");
  const times=rows.map((r,i)=>i%3===0?'<text x="'+
    (L+(i+.5)*dx).toFixed(1)+'" y="188" text-anchor="middle" font-size="11" fill="var(--muted)">'+
    esc(shortTime(r.czas))+'</text>':"").join("");
  return'<svg viewBox="0 0 '+W+' 198" preserveAspectRatio="xMidYMid meet" role="img" aria-label="SOC z planem i bez planu, godzinowa moc ładowania magazynu" >'+
   '<path d="M32 25H785 M32 88H785 M32 142H785" stroke="var(--line)" stroke-width="1"/>'+
   '<text x="3" y="27" font-size="11" fill="var(--muted)">SOC</text>'+
   '<text x="3" y="151" font-size="11" fill="var(--muted)">kW</text>'+
   bars+line("soc_bazowy_pct","#8998ac",true)+line("soc_plan_pct","#23a77d",false)+times+'</svg>';
 }
 render(){
  if(!this.shadowRoot) return;
  const e=this._hass?.states?.[this._cfg.entity],attrs=e?.attributes||{};
  const rows=Array.isArray(attrs.godziny)?attrs.godziny.slice(0,48).filter(x=>x&&typeof x==="object"):[];
  const groups=[rows.slice(0,24),rows.slice(24,48)];
  const day=Math.min(this._day,groups[1].length?1:0);this._day=day;
  const active=groups[day];
  const complete=e?.state==="gotowy"&&rows.length===48;
  const hasPlan=attrs.planowane_godziny>0;
  const compact=!!this._cfg.compact;
  const status=complete?"Pełna prognoza — proponowany harmonogram":
    hasPlan?"Niepełna prognoza — plan niezatwierdzony":
    "Brak wariantu ładowania — pokazuję scenariusz bazowy";
  const summary=[
   ["Ładowanie z sieci",complete?nfmt(num(attrs.energia_ladowania_z_sieci_kwh),2)+" kWh":"—"],
   ["Rozładowanie do domu",complete?nfmt(num(attrs.energia_rozladowania_do_domu_kwh),2)+" kWh":"—"],
   ["Import z planem",complete?nfmt(num(attrs.import_przy_planie_kwh),2)+" kWh":"—"],
   ["Import bez ładowania",complete?nfmt(num(attrs.import_bez_dodatkowego_ladowania_kwh),2)+" kWh":"—"],
  ];
  const table=compact?"":'<div class="table-wrap"><table><thead><tr>'+
   '<th>Godzina</th><th>Praca magazynu</th><th>Ład. sieć</th><th>Ład. PV</th>'+
   '<th>Rozł.</th><th>Import</th><th>SOC plan / bez</th></tr></thead><tbody>'+
   active.map(r=>{
    const mode={ladowanie_z_sieci:"Ładowanie z sieci",ladowanie_z_pv:"Ładowanie PV",
      rozladowanie:"Rozładowanie",spoczynek:"Spoczynek",brak_planu:"Brak planu"}[r.tryb]||"—";
    return'<tr><td>'+esc(shortTime(r.czas))+'</td><td>'+esc(mode)+'</td>'+
     '<td>'+esc(nfmt(num(r.ladowanie_siec_kwh),2))+'</td>'+
     '<td>'+esc(nfmt(num(r.ladowanie_pv_kwh),2))+'</td>'+
     '<td>'+esc(nfmt(num(r.rozladowanie_kwh),2))+'</td>'+
     '<td>'+esc(nfmt(num(r.import_plan_kwh),2))+'</td>'+
     '<td>'+esc(num(r.soc_plan_pct)===null?"—":nfmt(num(r.soc_plan_pct),0)+"%")+
     ' / '+esc(num(r.soc_bazowy_pct)===null?"—":nfmt(num(r.soc_bazowy_pct),0)+"%")+'</td></tr>';
   }).join("")+'</tbody></table></div>';
  const css=[
   ':host{--surface:var(--ha-card-background,var(--card-background-color,#fff));'+
   '--text:var(--primary-text-color,#15272f);--muted:var(--secondary-text-color,#6c7b88);'+
   '--line:var(--divider-color,#e3e9ed);--soft:var(--secondary-background-color,#f4f6f8);display:block;color:var(--text);font:inherit}',
   '*{box-sizing:border-box}ha-card{display:block;border:1px solid var(--line);border-radius:15px;background:var(--surface);padding:14px;box-shadow:none}',
   'header{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;flex-wrap:wrap}',
   'h2{margin:0 0 3px;font-size:15px}p{margin:0;font-size:11px;color:var(--muted);line-height:1.55}',
   '.days{display:flex;gap:4px}.days button{background:var(--soft);border:1px solid var(--line);'+
   'border-radius:8px;padding:7px 10px;color:var(--text);font:inherit;cursor:pointer;font-size:11px}',
   '.days button[aria-pressed="true"]{border-color:#22a47e;color:#15916d;font-weight:700}',
   '.legend{display:flex;flex-wrap:wrap;gap:7px 12px;margin:10px 0;font-size:10px;color:var(--muted)}',
   '.legend b{display:inline-block;width:9px;height:9px;margin-right:4px;border-radius:3px;background:#e5a43c}',
   '.legend .p b{background:#2eae80}.legend .d b{background:#3b8eb5}.legend .soc b{background:#23a77d}',
   '.legend .base b{background:#8998ac}', 'svg{width:100%;height:auto;display:block;max-height:170px}',
   '.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin-top:8px}',
   '.summary div{padding:9px;background:var(--soft);border-radius:10px;min-width:0}',
   '.summary small{font-size:10px;color:var(--muted);display:block;line-height:1.3}',
   '.summary strong{font-size:15px;display:block;white-space:nowrap}',
   '.notice{font-size:11px;color:var(--muted);margin-top:10px;line-height:1.5}',
   '.empty{padding:18px;text-align:center;color:var(--muted);font-size:12px}',
   '.table-wrap{overflow:auto;max-height:320px;margin-top:11px;border:1px solid var(--line);border-radius:9px}',
   'table{border-collapse:collapse;width:100%;font-size:11px}th,td{text-align:left;white-space:nowrap;padding:7px 10px;border-bottom:1px solid var(--line)}',
   'th{font-size:10px;color:var(--muted);position:sticky;top:0;background:var(--surface)}',
   '@media(max-width:520px){ha-card{padding:10px}.summary{grid-template-columns:repeat(2,minmax(0,1fr))}'+
   '.days button{padding:6px 8px}}',
  ].join("");
  this.shadowRoot.innerHTML='<style>'+css+'</style><ha-card>'+
   '<header><div><h2>'+esc(compact?"Praca magazynu — 48h":"Godzinowy harmonogram magazynu — 48h")+'</h2>'+
   '<p>'+esc(status)+'</p></div><div class="days">'+
   [0,1].map(i=>'<button type="button" data-day="'+i+'" aria-pressed="'+(i===day)+
     '" '+(groups[i].length?'':'disabled')+'>'+esc(groups[i][0]?dateLabel(groups[i][0].czas):"Dzień "+(i+1))+
     '</button>').join("")+'</div></header>'+
   '<div class="legend"><span><b></b>Ład. sieć</span><span class="p"><b></b>Ład. PV</span>'+
   '<span class="d"><b></b>Rozładowanie</span><span class="soc"><b></b>SOC plan</span>'+
   '<span class="base"><b></b>SOC bez planu</span></div>'+
   this._chart(active)+
   '<div class="summary">'+summary.map(([k,v])=>'<div><small>'+esc(k)+'</small><strong>'+esc(v)+'</strong></div>').join("")+
   '</div>'+table+
   '<p class="notice">'+esc(attrs.przyczyna||"")+
   ' · Wszystkie godziny są prognozą. Brak wykonanych poleceń do falownika Deye.</p></ha-card>';
  this.shadowRoot.querySelectorAll("button[data-day]").forEach(button=>{
   button.addEventListener("click",()=>{this._day=Number(button.dataset.day);this.render();});
  });
 }
}
customElements.define(TAG,EstadiPlan);
window.customCards=window.customCards||[];
if(!window.customCards.some(x=>x.type===TAG))
 window.customCards.push({type:TAG,name:"ESTADI — godzinowy plan 48h",description:"Plan ładowania vs brak ładowania; wyłącznie symulacja",preview:true});
})();