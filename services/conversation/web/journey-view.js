"use strict";
(function(root) {
  const $=id=>document.getElementById(id),M=root.JourneyModel;
  const n=(tag,text="",cls="")=>{const e=document.createElement(tag);e.textContent=text;e.className=cls;return e;};
  const fmt=value=>M.finite(value) ? value.toLocaleString("en-IN",{maximumFractionDigits:2}) : "Unavailable";
  const ms=value=>M.finite(value) ? `${fmt(value)} ms` : "Unavailable";
  const age=value=>M.finite(value) ? `${fmt(value)} s` : "Unavailable";
  const stamp=value=>M.time(value)!==null ? new Date(value).toISOString().replace("T"," ").replace("Z"," UTC") : "Unavailable";
  const short=value=>value ? String(value).slice(0,8)+"…" : "Unavailable";
  const mib=value=>M.finite(value) ? `${fmt(value/1048576)} MiB` : "Unavailable";
  const json=value=>JSON.stringify(value ?? "Unavailable",null,2);
  function fields(target,values) {
    const e=$(target);if(!e)return;e.replaceChildren();
    const dl=e.tagName==="DL" ? e : n("dl","","inspector-fields");
    if(dl!==e)e.classList.remove("inspector-fields");
    for(const [label,value] of values) dl.append(n("dt",label),n("dd",value===null || value===undefined ? "Unavailable" : String(value)));
    if(dl!==e)e.append(dl);
  }
  function rows(target,values,message="No observations available.") {
    const e=$(target);if(!e)return;e.replaceChildren();
    if(!values.length){const tr=n("tr"),td=n("td",message);td.colSpan=8;tr.append(td);e.append(tr);return;}
    for(const row of values){const tr=n("tr");for(const value of row)tr.append(n("td",value===null || value===undefined ? "Unavailable" : String(value)));e.append(tr);}
  }
  function svg(tag,attributes={},text) {
    const e=document.createElementNS("http://www.w3.org/2000/svg",tag);
    for(const [k,v]of Object.entries(attributes))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;
  }
  function line(target,values,label,colour="#648568") {
    const e=$(target);if(!e)return;e.replaceChildren();const points=values.map((v,i)=>({v,i})).filter(p=>M.finite(p.v));
    if(!points.length){e.append(n("p","No qualified samples. Missing or unqualified timing is not plotted.","empty"));return;}
    const w=650,h=190,l=50,r=16,t=15,b=30,max=Math.max(1,...points.map(p=>p.v)),graph=svg("svg",{viewBox:`0 0 ${w} ${h}`,role:"img","aria-label":label});
    graph.append(svg("title",{},label));
    for(let i=0;i<=4;i++){const y=h-b-(h-t-b)*i/4;graph.append(svg("line",{x1:l,y1:y,x2:w-r,y2:y,stroke:"#e5eadc"}),svg("text",{x:l-8,y:y+4,"text-anchor":"end"},fmt(max*i/4)));}
    const x=i=>l+(values.length===1 ? (w-l-r)/2 : i/(values.length-1)*(w-l-r)),y=v=>h-b-v/max*(h-t-b);
    let segment=[];const draw=()=>{if(segment.length>1)graph.append(svg("polyline",{points:segment.join(" "),fill:"none",stroke:colour,"stroke-width":2}));segment=[];};
    values.forEach((v,i)=>{if(!M.finite(v)){draw();return;}segment.push(`${x(i)},${y(v)}`);const dot=svg("circle",{cx:x(i),cy:y(v),r:3,fill:colour});dot.append(svg("title",{},`Sample ${i+1}: ${fmt(v)}`));graph.append(dot);});draw();
    graph.append(svg("text",{x:l,y:h-8},"First observed sample"),svg("text",{x:w-r,y:h-8,"text-anchor":"end"},"Most recent"));e.append(graph);
  }
  function quantiles(target,q={}){const e=$(target);if(!e)return;e.replaceChildren();for(const [k,label]of [["p50_ms","p50"],["p95_ms","p95"],["p99_ms","p99"]]){const d=n("div",label);d.append(n("strong",ms(q[k])));e.append(d);}}
  function boundaries(data) {
    const out=data.outboxes || [],infra=data.infrastructure || {},lag=infra.lag,pending=data.pending_gold || {},gold=data.manifests?.gold;
    const allOut=out.length===5 && out.every(r=>r.status==="observed" && M.finite(r.pending)),total=allOut ? out.reduce((s,r)=>s+r.pending,0) : null;
    const analyticsLag=(lag || []).filter(r=>r.group===`${data.namespace}.analytics.v1`);
    const knownLag=analyticsLag.length>=5 && analyticsLag.every(r=>M.finite(r.lag)),lagTotal=knownLag ? analyticsLag.reduce((s,r)=>s+r.lag,0) : null;
    const e=$("boundary-cards");if(e){e.replaceChildren();const cards=[
      ["Before Kafka",total,"Pending outbox events · five producer services"],
      ["Kafka consumption",lagTotal,"Committed analytics-group lag · all expected partitions"],
      ["After sink processing",pending.count,`Awaiting active Gold · oldest ${age(pending.oldest_age_seconds)}`],
      ["Final output",gold?.generation,`Active Gold generation · ${stamp(gold?.created_at)}`]];
      cards.forEach(([label,value,note],i)=>{const d=n("article","",`boundary-card ${!M.finite(value) ? "missing" : i<3 && value>0 ? "warn" : ""}`);d.append(n("span",label),n("strong",fmt(value)),n("small",note));e.append(d);});}
    if($("boundary-health"))$("boundary-health").textContent=!allOut || !knownLag || pending.count===null || pending.count===undefined || !gold ? "Some boundaries are unavailable. Overall pipeline health is not established." : total || lagTotal || pending.count ? "Backlog is observed. Low Kafka lag alone does not establish Gold freshness; inspect each boundary." : "All observed backlogs are zero at this snapshot. This is a point-in-time observation.";
    rows("outbox-table",out.map(r=>[r.service,fmt(r.pending),r.pending===0 ? "No pending events" : age(r.oldest_pending_age_seconds),`${r.status} · ${stamp(r.observed_at)}`]));
    rows("journey-lag",(lag || []).map(r=>[r.group,r.topic,r.partition,fmt(r.log_end_next_offset),fmt(r.committed_next_offset),fmt(r.lag)]));
    rows("journey-resources",(infra.resources || []).map(r=>[`${r.service} · ${r.container_id}`,r.status==="warming_up" ? "First sample · warming up" : `${fmt(r.cpu_percent)}% / ${fmt(r.allocated_cpus)} CPU`,`${mib(r.memory_bytes)} / ${mib(r.memory_limit_bytes)}`,mib(r.memory_peak_bytes),fmt(r.oom_kill_count),r.status]));
    if($("resource-note"))$("resource-note").textContent=`Observed ${stamp(infra.observed_at)} · CPU relative to allocation · cgroup memory includes page cache · first samples warm up. ${!infra.resources ? "Resource collection unavailable." : ""}`;
    const latency=data.latency || M.latency(data.events || [],data.clock || {});
    quantiles("producer-quantiles",latency.producer_to_gold);quantiles("schedule-quantiles",latency.schedule_to_gold);
    const counts=$("completion-counts");if(counts){counts.replaceChildren();for(const [label,key]of [["Samples","sample_count"],["Completed","completed_count"],["Unresolved","unresolved_count"]]){const d=n("div",label);d.append(n("strong",fmt(key==="sample_count" ? latency.producer_to_gold?.sample_count : latency[key])));counts.append(d);}}
    if($("quantile-note"))$("quantile-note").textContent=`Completed-only nearest-rank quantiles · clock ${data.clock?.status || "unavailable"}. ${latency.cohort_p99_established ? "Observed cohort p99 has sufficient completion coverage." : "Complete-cohort p99 is not established."} Bounded namespace sample, not a sustained benchmark.`;
    rows("latency-breakdown",(latency.breakdown || []).slice(-30).map(r=>[`${r.event_type || "Event"} · ${short(r.event_id)}`,ms(r.relay_to_observation_ms),ms(r.ingestion_ms),ms(r.publication_ms),ms(r.producer_to_gold_ms)]));
    line("end-to-end-chart",(latency.breakdown || []).map(r=>r.producer_to_gold_ms),"Observed producer-to-active-Gold milliseconds");
    const completion=$("completion-chart");if(completion){completion.replaceChildren();const total=latency.cohort_count || 0,done=latency.completed_count || 0; if(total){const graph=svg("svg",{viewBox:"0 0 340 150",role:"img","aria-label":`${done} completed and ${latency.unresolved_count} unresolved events`});graph.append(svg("rect",{x:15,y:25,width:310,height:22,rx:8,fill:"#f2e6cf"}),svg("rect",{x:15,y:25,width:310*done/total,height:22,rx:8,fill:"#648568"}),svg("text",{x:15,y:80},`${fmt(done)} completed / ${fmt(total)} observed unique IDs`),svg("text",{x:15,y:105},`${fmt(latency.unresolved_count)} unresolved`));completion.append(graph);}else completion.append(n("p","No observed cohort.","empty"));}
    const workload=data.workload || (data.lab?.run?.namespace===data.namespace ? data.lab.run : null);
    const rates=workload ? M.workloadRates(workload) : data.rates || M.workloadRates(null),target=$("workload-rates");
    if(target){target.replaceChildren();for(const [label,key]of [["Offered traffic","offered_per_second"],["Admitted traffic","admitted_per_second"],["Completed Gold goodput","gold_goodput_per_second"]]){const row=n("div","","rate-row");row.append(n("span",label),n("strong",M.finite(rates[key]) ? `${fmt(rates[key])} / s` : "Unavailable"));target.append(row);}}
    if($("rates-note"))$("rates-note").textContent=rates.basis;
  }
  root.JourneyView={$: $,n,fmt,ms,age,stamp,short,mib,json,fields,rows,svg,line,quantiles,boundaries};
})(window);
