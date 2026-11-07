/* ESTADI compact operational cockpit. Read-only: never send commands to Deye. */
(() => {
 "use strict";
 const TAG="estadi-energy-control-card";
 if(customElements.get(TAG))return;
 const esc=(v)=>String(v==null?"":v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const num=(v)=>{if(v===null||v===undefined||v===""||typeof v==="boolean")return null;
   if(/^(unknown|unavailable|none|null|nan)$/i.test(String(v)))return null;
   const n=Number(String(v).replace(",","."));return Number.isFinite(n)?n:null;};
 const fmt=(n,d=1)=>n==null?"—":n.toLocaleString("pl-PL",{maximumFractionDigits:d});
 const power=(w)=>w===null?"—":Math.abs(w)<1000?fmt(w,0)+" W":fmt(w/1000,2)+" kW";
 const clock=(v)=>{const d=new Date(v);return v&&Number.isFinite(d.getTime())?
   d.toLocaleString("pl-PL",{timeZone:"Europe/Warsaw",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}):"—";};
 const label=(v)=>v==null||v==="unknown"||v==="unavailable"?"Brak danych":String(v).replace(/_/g," ");
 const svgLine=(rows,kind,mode)=> {
   if(!Array.isArray(rows)||rows.length<2)return'<div class="empty">Brak historii do wykresu</div>';
   const max=kind==="soc_do"?100:Math.max(0.01,...rows.flatMap(r=>[num(r.forecast_kwh)||0,num(r.actual_kwh)||0]));
   const keys=kind==="soc_do"?["soc_do"]:["forecast_kwh","actual_kwh"];
   const paths=keys.map((key,j)=>{
     let segments=[],pts=[];
     rows.forEach((r,i)=>{
       const v=num(r[key]),coverage=num(r.coverage_pct);
       if(v===null||(key==="actual_kwh"&&coverage!==null&&coverage<75)){
         if(pts.length>=2)segments.push(pts.join(" "));pts=[];return;
       }
       const x=5+390*i/(rows.length-1),y=86-75*v/max;
       pts.push(x.toFixed(1)+","+y.toFixed(1));
     });
     if(pts.length>=2)segments.push(pts.join(" "));
     const color=kind==="soc_do"?"#21a87b":j===0?"#e4a43b":"#248eab";
     return segments.map(p=>'<polyline points="'+p+'" fill="none" stroke="'+color+
       '" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>').join("");
   }).join("");
   return '<svg viewBox="0 0 400 100" preserveAspectRatio="none" role="img" aria-label="'+
      esc(mode)+'"><path d="M5 86H395" stroke="var(--line)"/>'+paths+'</svg>';
 };
 class Control extends HTMLElement{
   constructor(){super();this.attachShadow({mode:"open"});this._config={};this._hass=null;this._signature="";}
   static getStubConfig(){return{};}
   getCardSize(){return 10;}
   getGridOptions(){return{columns:"full",rows:"auto"};}
   setConfig(v){this._config=v||{};this._signature="";this.render();}
   set hass(h){
     this._hass=h;
     if(!h?.states)return;
     const sig=Object.entries(this._config).filter(([k])=>k.startsWith("entity_")).map(([k,id])=>{
       const x=h.states[id];return k+":"+(x?x.state+":"+x.last_updated:"missing");
     }).join("|");
     if(sig!==this._signature){this._signature=sig;this.render();}
   }
   entity(k){return this._hass?.states?.[this._config["entity_"+k]]||null;}
   state(k){return this.entity(k)?.state??null;}
   n(k,min=-Infinity,max=Infinity){const v=num(this.state(k));return v!==null&&v>=min&&v<=max?v:null;}
   metric(label,v,desc){
     return '<div class="metric"><span>'+esc(label)+'</span><strong>'+esc(v)+'</strong>'+
       '<small>'+esc(desc)+'</small></div>';
   }
   node(name,val,detail,icon,cls){
     return '<div class="node '+cls+'"><ha-icon icon="mdi:'+icon+'"></ha-icon><div>'+
       '<span>'+esc(name)+'</span><strong>'+esc(val)+'</strong><small>'+esc(detail)+
       '</small></div></div>';
   }
   render(){
     if(!this.shadowRoot)return;
     const pv=this.n("pv",0),load=this.n("home",0),soc=this.n("soc",0,100);
     const battery=this.n("battery_power"),losses=this.n("losses",0);
     const batteryState=String(this.state("battery_state")||"").toLowerCase();
     const batteryName=batteryState.includes("discharg")?"Rozładowanie":
       batteryState.includes("charg")?"Ładowanie":
       batteryState==="idle"||batteryState.includes("standby")?"Spoczynek":
       "Stan baterii nieznany";
     const ev=this.n("ev",0),pump=this.n("pump",0),importKw=this.n("grid_import",0);
     const rawKw=this.n("grid_raw"),gridLimit=this.n("grid_limit",0);
     const headroom=this.n("grid_headroom"),gridStatus=label(this.state("grid_status"));
     const batteryDetail=battery===null?"Brak odczytu":"Znak mocy · niepotwierdzony kierunek";
     const gridValue=importKw===null?(rawKw===null?"—":power(rawKw*1000)+" *"):power(importKw*1000);
     const gridDetail=importKw===null?"Odczyt ze znakiem (nie import)":"Import potwierdzony";
     const planStatus=this.state("smart_charge_status");
     const start=this.state("smart_charge_start"),finish=this.state("smart_charge_finish");
     const planned=planStatus==="wstepny_plan"&&this.n("smart_charge_power",0)!==null&&start;
     const simHours=this.n("sim_hours",0,48),simStatus=this.state("sim_status");
     const ready=simStatus==="gotowa"&&simHours!==null&&simHours>=47.75;
     const simReason=this.entity("sim_status")?.attributes?.przyczyna||"";
     const planReason=this.entity("smart_charge_status")?.attributes?.przyczyna||"";
     const rows=this.entity("sim_status")?.attributes?.harmonogram_48h;
     const history=this.entity("history_status")?.attributes?.godziny;
     const coverage=simHours===null?0:Math.max(0,Math.min(100,simHours/48*100));
     const chargeKW=this.n("smart_charge_power",0),chargeKWH=this.n("smart_charge_energy",0);
     const target=this.n("smart_charge_target",0,100),endSOC=this.n("sim_soc_end",0,100);
     const pvKwh=this.n("sim_pv_kwh",0),gridKwh=this.n("sim_grid_kwh",0);
     const planTitle=planned?"Plan doradczy gotowy":ready?"Symulacja gotowa, plan niedostępny":"Brak pełnego planu ładowania";
     const css=[
     ':host{--surface:var(--ha-card-background,var(--card-background-color,#fff));--text:var(--primary-text-color,#142330);--muted:var(--secondary-text-color,#62707c);--line:var(--divider-color,#e3e9ef);--soft:var(--secondary-background-color,#f4f6f8);color:var(--text);display:block;font:inherit}',
     '*{box-sizing:border-box}ha-card{background:transparent;border:0;box-shadow:none}',
     '.shell{max-width:1450px;margin:auto;padding:10px;display:grid;gap:10px}',
     '.top{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:2px}',
     '.brand{display:flex;align-items:center;gap:10px}.logo{background:#143f38;color:#b9f1dc;width:32px;height:32px;border-radius:10px;display:grid;place-items:center;font-size:20px;font-weight:800}',
     'h1{margin:0;font-size:19px;letter-spacing:-.02em}.sub{font-size:11px;color:var(--muted)}',
     '.badge{font-size:11px;padding:6px 10px;border:1px solid var(--line);border-radius:30px;color:var(--muted)}',
     '.cols{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,.88fr);gap:10px}',
     '.lower{display:grid;grid-template-columns:1fr 1fr;gap:10px}',
     '.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:14px;min-width:0}',
     'h2{font-size:15px;margin:0 0 12px;letter-spacing:-.015em}',
     '.flow{display:grid;grid-template-columns:minmax(0,1fr) 76px minmax(0,1fr);grid-template-rows:60px 76px 60px;gap:6px}',
     '.node{border:1px solid var(--line);border-radius:11px;display:flex;gap:7px;align-items:center;padding:8px;min-width:0}',
     '.node ha-icon{--mdc-icon-size:21px;color:#219879;flex-shrink:0}.node span,.node small{font-size:10px;display:block;color:var(--muted);line-height:1.25}',
     '.node strong{font-size:18px;display:block;font-weight:750;white-space:nowrap;font-variant-numeric:tabular-nums}',
     '.node small{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}',
     '.pv{grid-column:1;grid-row:1}.pv ha-icon{color:#ddaa30}',
     '.grid{grid-column:1;grid-row:2}.grid ha-icon{color:#5c86cb}',
     '.home{grid-column:3;grid-row:2}.home ha-icon{color:#29a99e}',
     '.losses{grid-column:1;grid-row:3}.losses ha-icon{color:#c2954a}',
     '.battery{grid-column:3;grid-row:3}',
     '.inv{grid-column:2;grid-row:2;border-radius:11px;background:#163f39;color:#e6fff1;display:grid;place-items:center;align-content:center;gap:1px}',
     '.inv ha-icon{--mdc-icon-size:24px;color:#9bd5c3}.inv b{font-size:11px}.inv small{color:#aad6c8;font-size:9px}',
     '.pathpv{grid-column:2;grid-row:1}.pathbat{grid-column:2;grid-row:3}.connector{color:var(--muted);display:grid;place-items:center;font-size:11px}',
     '.details{display:flex;gap:7px 15px;flex-wrap:wrap;margin-top:11px;font-size:11px;color:var(--muted)}.details b{color:var(--text)}',
     '.foot{font-size:10.5px;line-height:1.5;color:var(--muted);margin-top:9px}',
     '.alert{background:rgba(201,144,46,.075);border:1px solid rgba(201,144,46,.24);padding:10px 12px;border-radius:10px;font-size:12px;line-height:1.45;margin-bottom:10px}',
     '.alert b{display:block;margin-bottom:3px}',
     '.metrics{display:grid;grid-template-columns:1fr 1fr;gap:7px}',
     '.metric{background:var(--soft);border-radius:10px;padding:10px 12px;min-width:0}',
     '.metric span,.metric small{display:block;font-size:10px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
     '.metric strong{display:block;font-size:18px;font-variant-numeric:tabular-nums;white-space:nowrap}',
     '.chart-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px}',
     '.chart-summary div{padding:8px 6px;border:1px solid var(--line);border-radius:8px;min-width:0}',
     '.chart-summary span{display:block;color:var(--muted);font-size:10px}.chart-summary b{font-size:13px;white-space:nowrap;display:block}',
     '.meter{height:6px;border-radius:6px;background:var(--soft);margin:11px 0;overflow:hidden}.meter i{display:block;height:100%;background:#269f7a}',
     'svg{display:block;width:100%;height:94px}.empty{padding:24px 5px;text-align:center;font-size:11px;color:var(--muted)}',
     '.legend{display:flex;gap:13px;font-size:10px;color:var(--muted)}.legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;background:#e4a43b}.legend .real{background:#248eab}',
     '@media(max-width:900px){.cols,.lower{grid-template-columns:1fr}}',
     '@media(max-width:500px){.shell{padding:4px;gap:8px}.card{padding:10px;border-radius:12px}.flow{grid-template-columns:minmax(0,1fr) 57px minmax(0,1fr);gap:4px}.node{gap:4px;padding:5px}.node strong{font-size:15px}.node ha-icon{--mdc-icon-size:16px}.node span,.node small{font-size:9px}.metric strong{font-size:16px}.chart-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}'
     ].join("");
     this.shadowRoot.innerHTML='<style>'+css+'</style><ha-card><main class="shell">'+
      '<header class="top"><div class="brand"><div class="logo">E</div><div><h1>Centrum energii</h1><div class="sub">ESTADI · Pomiary i plan ładowania</div></div></div>'+
      '<span class="badge">Sterowanie Deye: WYŁĄCZONE</span></header>'+
      '<section class="cols"><div class="card"><h2>Przepływy energii · teraz</h2>'+
      '<div class="flow">'+
      this.node("Fotowoltaika",power(pv),"Produkcja PV","solar-power","pv")+
      '<div class="connector pathpv">↓ PV</div>'+
      this.node("Sieć",gridValue,gridDetail,"transmission-tower","grid")+
      '<div class="inv"><ha-icon icon="mdi:power-plug"></ha-icon><b>DEYE</b><small>3-fazowy</small></div>'+
      this.node("Cały dom",power(load),"Deye Load","home-lightning-bolt-outline","home")+
      this.node("Straty",power(losses),"Falownik","heat-wave","losses")+
      '<div class="connector pathbat">↕ BAT</div>'+
      this.node("Magazyn",soc===null?"—":fmt(soc,0)+"%",batteryName+" · "+power(battery),"battery-medium","battery")+
      '</div><div class="details"><span>EV <b>'+esc(power(ev))+'</b></span><span>Pompa <b>'+esc(power(pump))+
      '</b></span><span>Limit <b>'+esc(gridLimit===null?"—":fmt(gridLimit,1)+" kW")+
      '</b></span><span>Zapas <b>'+esc(headroom===null?"—":fmt(headroom,2)+" kW")+'</b></span></div>'+
      '<div class="foot">* Jeżeli kierunek sieci nie jest potwierdzony, pokazuję surową moc ze znakiem, a nie import. Moc baterii także zachowuje znak do kalibracji. EV i pompa są już w Deye Load.</div>'+
      '</div><div class="card"><h2>Plan magazynu · dziś i noc</h2>'+
      '<div class="alert"><b>'+esc(planTitle)+'</b>'+
      esc(planned?"To propozycja, nie wykonane sterowanie.":planReason||simReason||"Brakuje kompletnej prognozy lub danych bezpieczeństwa.")+
      '</div><div class="metrics">'+
      this.metric("Start",planned?clock(start):"—","Okno taryfy")+
      this.metric("Moc ładowania",planned?fmt(this.n("smart_charge_power",0),2)+" kW":"—","Nie wykonana")+
      this.metric("Dokup do magazynu",planned?fmt(this.n("smart_charge_energy",0),2)+" kWh":"—","Energia z sieci")+
      this.metric("Docelowy SOC",planned?fmt(this.n("smart_charge_target",0,100),0)+"%":"—","Obecnie "+(soc===null?"—":fmt(soc,0)+"%"))+
      '</div><div class="details"><span>Koniec <b>'+esc(planned?clock(finish):"—")+
      '</b></span><span>Tania strefa <b>'+esc(clock(this.state("next_cheap")))+'</b></span></div>'+
      '<div class="foot">Plan wyłącznie doradczy. Brak danych nie jest zerem ani potwierdzeniem możliwości ładowania.</div>'+
      '</div></section><section class="lower">'+
      '<div class="card"><h2>Prognoza 48h · SOC i energia</h2>'+
      '<div class="chart-summary"><div><span>PV</span><b>'+esc(ready?fmt(pvKwh,1)+" kWh":"—")+'</b></div>'+
      '<div><span>Zakup z sieci</span><b>'+esc(ready?fmt(gridKwh,1)+" kWh":"—")+'</b></div>'+
      '<div><span>SOC na końcu</span><b>'+esc(ready?fmt(endSOC,0)+"%":"—")+'</b></div>'+
      '<div><span>Dostępność</span><b>'+esc(simHours===null?"—":fmt(simHours,1)+"/48 h")+'</b></div></div>'+
      '<div class="meter"><i style="width:'+coverage+'%"></i></div>'+
      svgLine(rows,"soc_do","Prognozowany poziom magazynu SOC")+
      '<div class="foot">'+esc(ready?"Pełna prognoza; nie jest pomiarem.":simReason||"Niepełna prognoza, nie pokazuję sum 48h.")+'</div></div>'+
      '<div class="card"><h2>Prognoza kontra pomiar · wczoraj</h2>'+
      svgLine(history,"history","Rzeczywista produkcja PV względem prognozy")+
      '<div class="legend"><span><i></i>Prognoza PV</span><span><i class="real"></i>Pomiar PV</span></div>'+
      '<div class="foot">Pomijamy godziny bez odczytu lub z niską kompletnością — żadnych dopisywanych zer.</div></div>'+
      '</section></main></ha-card>';
   }
 }
 customElements.define(TAG,Control);
 window.customCards=window.customCards||[];
 window.customCards.push({type:TAG,name:"ESTADI — Centrum operacyjne",description:"Kompaktowy schemat mocy i plan bez sterowania",preview:true});
})();