"use strict";
(() => {
  const $=id=>document.getElementById(id), history=[];
  let busy=false;
  const cell=value=>{const e=document.createElement('td');e.textContent=value ?? 'Unavailable';return e;};
  const mib=v=>v===null || v===undefined ? 'Unavailable' : `${(v/1048576).toFixed(1)} MiB`;
  async function refresh(manual=false) {
    if(busy || document.hidden || (window.dashboardObservationPaused && !manual))return;
    busy=true;
    try {
      const response=await fetch('http://127.0.0.1:8010/infrastructure',{
        credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(22000)});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const data=await response.json();
      $('infra-state').textContent=`Observed ${new Date(data.observed_at).toLocaleTimeString()} · ${data.namespace} · ${data.complete ? 'Complete snapshot' : 'Partial snapshot / CPU warming up'}`;
      for(const [target,rows,values] of [
        ['infra-lag',data.lag,r=>[r.group,r.topic,r.partition,r.log_end_next_offset,r.committed_next_offset,r.lag]],
        ['infra-resources',data.resources,r=>[r.service,r.cpu_percent===null ? 'Unavailable / warming up' : `${r.cpu_percent.toFixed(1)}% / ${r.allocated_cpus} CPU`,`${mib(r.memory_bytes)} / ${mib(r.memory_limit_bytes)}`,mib(r.memory_peak_bytes),r.oom_kill_count,r.status]]
      ]) {
        const body=$(target);body.replaceChildren();
        if(!rows?.length){const tr=document.createElement('tr'),td=cell('Unavailable');td.colSpan=6;tr.append(td);body.append(tr);}
        for(const row of rows || []){const tr=document.createElement('tr');values(row).forEach(v=>tr.append(cell(v)));body.append(tr);}
      }
      const known=data.lag?.length && data.lag.every(r=>r.lag!==null);
      history.push({at:data.observed_at,lag:known ? data.lag.reduce((n,r)=>n+r.lag,0) : null});
      if(history.length>60)history.shift();
      const chart=$('infra-lag-chart');chart.replaceChildren();
      const svg=(tag,attrs={},text)=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;};
      const graph=svg('svg',{viewBox:'0 0 680 210',role:'img','aria-label':'Total committed consumer lag, measured records over time'});
      const start=Date.parse(history[0].at),duration=Math.max(1,Date.parse(history.at(-1).at)-start),max=Math.max(1,...history.map(p=>p.lag ?? 0));
      graph.append(svg('line',{x1:50,y1:175,x2:660,y2:175,stroke:'#b3beb6'}));
      let segment=[];const draw=()=>{if(segment.length>1)graph.append(svg('polyline',{points:segment.join(' '),fill:'none',stroke:'#356b50','stroke-width':2.5}));segment=[];};
      for(const p of history){if(p.lag===null){draw();continue;}const x=50+(Date.parse(p.at)-start)/duration*610,y=175-p.lag/max*150;segment.push(`${x},${y}`);const dot=svg('circle',{cx:x,cy:y,r:3,fill:'#356b50'});dot.append(svg('title',{},`${p.at}: ${p.lag} records`));graph.append(dot);}draw();
      graph.append(svg('text',{x:5,y:25},`${max} records`),svg('text',{x:50,y:200},new Date(history[0].at).toLocaleTimeString()),svg('text',{x:660,y:200,'text-anchor':'end'},new Date(history.at(-1).at).toLocaleTimeString()));chart.append(graph);
      window.dispatchEvent(new CustomEvent('infrastructure-snapshot',{detail:data}));
    } catch(e) {
      $('infra-state').textContent=`Infrastructure unavailable; displayed values are stale. ${e.message}. Start the local helper.`;
    } finally {busy=false;}
  }
  $('infra-refresh').addEventListener('click',()=>refresh(true));
  window.addEventListener('observation-refresh',()=>refresh(true));
  window.addEventListener('observation-pause',e=>{if(!e.detail.paused)refresh();});
  $('infra-export')?.addEventListener('click',()=>{
    if(!window.latestInfrastructure)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify({snapshot:window.latestInfrastructure,lag_history:history},null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='infrastructure-observations.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  window.addEventListener('infrastructure-snapshot',e=>{window.latestInfrastructure=e.detail;});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  setInterval(refresh,5000);refresh();
})();
