"use strict";
(function(root) {
  const finite=v=>typeof v==="number" && Number.isFinite(v);
  const quantile=(values,q)=>{const a=values.filter(finite).sort((a,b)=>a-b);return a.length ? a[Math.ceil(a.length*q)-1] : null;};
  function recentEvents(data) {
    const end=Date.parse(data.observed_at),start=end-3600000;
    return (data.events || []).filter(e=>Date.parse(e.produced_at)>=start && Date.parse(e.produced_at)<=end)
      .sort((a,b)=>Date.parse(a.produced_at)-Date.parse(b.produced_at));
  }
  function metrics(data) {
    const turns=data.activity?.turns || [],m=data.session;
    const retrieval=turns.filter(t=>t.search_executed && finite(t.search_ms)).map(t=>t.search_ms);
    // Use completed event-time minutes only; never divide a partial minute by 60.
    const cutoff=Math.floor(Date.parse(data.checked_at)/60000)*60000;
    const minutes=(data.pipeline?.minutes || []).filter(p=>Date.parse(p.minute)<cutoff && Date.parse(p.minute)>=cutoff-300000);
    return {retrievalP95:quantile(retrieval,.95),retrievalCount:retrieval.length,
      eventRate:minutes.length ? minutes.reduce((n,p)=>n+p.events,0)/minutes.length : null,
      minuteCount:minutes.length,failures:m.sampled_turns ? 100*m.dependency_errors/m.sampled_turns : null};
  }
  if(typeof module==="object" && module.exports){module.exports={metrics,quantile,recentEvents};return;}
  const $=id=>document.getElementById(id);
  const n=(tag,text,cls="")=>{const e=document.createElement(tag);e.textContent=text;e.className=cls;return e;};
  const fmt=v=>finite(v) ? v.toLocaleString("en-IN",{maximumFractionDigits:1}) : "No samples";
  const ms=v=>!finite(v) ? "No samples" : v>=60000 ? `${fmt(v/60000)} min` : v>=1000 ? `${fmt(v/1000)} s` : `${fmt(v)} ms`;
  let app=null,pipe=null,infra=null;
  const staleSources=new Set();
  function cards() {
    if(!$("kpis"))return;
    const m=app?.session,s=app ? metrics(app) : {},q=pipe?.latency?.producer_to_gold;
    const lag=infra?.lag || [],known=lag.length>0 && lag.every(r=>finite(r.lag));
    const totals=[
      ["Events in Gold",app?.pipeline ? fmt(app.pipeline.events) : "Unavailable","Unique events · today, UTC","application"],
      ["Event throughput",finite(s.eventRate) ? `${fmt(s.eventRate)} / min` : "No samples",`Mean of ${s.minuteCount || 0} completed event-time minutes · not capacity`,"application"],
      ["Chat response · p95",ms(m?.turn_p95_ms),`${m?.sampled_turns ?? 0} saved turns · server-side request duration`,"application"],
      ["Retrieval · p95",ms(s.retrievalP95),`${s.retrievalCount || 0} attempts in latest 60 turns · includes timed failures`,"application"],
      ["LLM calls",m ? fmt(m.model_attempts) : "Unavailable",`Whole-session attempts · mean ${ms(m?.model_mean_ms)} in latest 500 turns`,"application"],
      ["Chat failures",finite(s.failures) ? `${fmt(s.failures)}%` : "No samples",`${m?.dependency_errors ?? 0} dependency errors / ${m?.sampled_turns ?? 0} turns · clarifications excluded`,"application"],
      ["Event → Gold · p95",ms(q?.p95_ms),`${q?.sample_count || 0} timed events · last hour, bounded sample`,"pipeline"],
      ["Kafka consumer lag",known ? `${fmt(lag.reduce((n,r)=>n+r.lag,0))}` : "Unavailable",known ? `${lag.length} group-partitions · uncommitted records` : "Waiting for a complete broker reading","infrastructure"]
    ];
    $("kpis").replaceChildren(...totals.map(([label,value,note,source])=>{
      const e=n("article","","kpi");e.dataset.source=source;
      const stamp=source==="application" ? app?.checked_at : source==="pipeline" ? pipe?.observed_at : infra?.observed_at;
      e.append(n("span",label,"label"),n("strong",value),n("p",note,"detail"));
      if(staleSources.has(source))e.append(n("span",stamp ? "Stale · refresh unavailable" : "Unavailable · retrying","metric-stale"));
      if(stamp)e.title=`Source observed ${new Date(stamp).toLocaleString()}`;
      return e;
    }));
  }
  function render(data) {
    app=data;staleSources.delete("application");cards();
    const turns=data.activity.turns;
    $("chat-chart-note").textContent=`Latest ${turns.length} saved turns in this browser's session. Total includes parsing and service calls; LLM and retrieval are components, not additional time. Gaps mean that step did not run.`;
    $("session-scope").textContent=`Chat: this browser's session · latest ${data.session.sampled_turns} turns (maximum 500)`;
    $("throughput-note").textContent=data.pipeline ? `Last 60 event-time minutes, UTC · Gold generation ${data.pipeline.generation}. Late arrivals may revise earlier bars; this is event activity, not measured processing capacity.` : "Analytics unavailable; no zero values inferred.";
    // Discrete minute buckets must look like buckets, not a smoothed arrival-rate curve.
    if(data.pipeline) eventBars(data.pipeline.minutes);
  }
  function eventBars(points) {
    const target=$("throughput-chart");if(!points.length)return;
    const svg=(tag,attrs={},text)=>{const e=document.createElementNS("http://www.w3.org/2000/svg",tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;};
    const g=svg("svg",{viewBox:"0 0 620 205",role:"img","aria-label":"Unique events per event-time minute; UTC, last hour"});
    const max=Math.max(1,...points.map(p=>p.events)),width=560/points.length;
    for(let i=0;i<=4;i++){const y=170-i*140/4;g.append(svg("line",{x1:48,y1:y,x2:610,y2:y,stroke:"#e1e7df"}),svg("text",{x:40,y:y+3,"text-anchor":"end"},fmt(max*i/4)));}
    points.forEach((p,i)=>{const bar=svg("rect",{x:48+i*width,y:170-p.events/max*140,width:Math.max(1,width-2),height:p.events/max*140,rx:1,fill:"#356b50"});bar.append(svg("title",{},`${p.minute}: ${p.events} unique events`));g.append(bar);});
    const label=p=>new Date(p.minute).toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit",timeZone:"UTC"});
    g.append(svg("text",{x:48,y:15},"events / minute"),svg("text",{x:48,y:195},label(points[0])),svg("text",{x:610,y:195,"text-anchor":"end"},label(points.at(-1))+" UTC"));
    target.replaceChildren(g);
  }
  function pipeline(data) {
    staleSources.delete("pipeline");
    const latency=root.JourneyModel.latency(recentEvents(data),data.clock || {});
    pipe={...data,latency};cards();
    root.JourneyView.quantiles("producer-quantiles",latency.producer_to_gold);
    $("completion-counts").replaceChildren(...[["Timed events",latency.producer_to_gold.sample_count],["Completed",latency.completed_count],["Waiting",latency.unresolved_count]].map(([label,value])=>{const e=n("div",label);e.append(n("strong",fmt(value)));return e;}));
    $("quantile-note").textContent=`Events created in the last hour · ${latency.producer_to_gold.sample_count} qualified timings / ${latency.cohort_count} observed unique events. Clock: ${data.clock?.status || "unavailable"}. Waiting events are shown above, excluded from percentiles. ${data.bounds?.source_truncated ? "Source history is bounded; this is not a complete traffic census." : ""}`;
    root.JourneyView.line("end-to-end-chart",latency.breakdown.map(r=>finite(r.producer_to_gold_ms) ? r.producer_to_gold_ms/1000 : null),"Event creation to active Gold, seconds; samples ordered by creation time");
    const graph=$("end-to-end-chart").querySelector("svg");
    if(graph){graph.prepend(root.JourneyView.svg("text",{x:50,y:10},"seconds / event sample"));}
    if($("retained-latency")){
      const full=data.latency;
      $("retained-latency").textContent=`Full retained history: ${full?.producer_to_gold?.sample_count ?? 0} timed events; event-to-Gold p95 ${ms(full?.producer_to_gold?.p95_ms)}. Includes import/startup traffic from earlier days. The main panel uses a rolling one-hour creation-time window; neither cohort includes missing timings in percentiles.`;
    }
  }
  function stale(source){staleSources.add(source);cards();}
  function exportSnapshot() {
    return {...app,dashboard_measurements:{schema_version:1,exported_at:new Date().toISOString(),
      stale_sources:[...staleSources],derived_application:app ? metrics(app) : null,
      pipeline:pipe ? {observed_at:pipe.observed_at,namespace:pipe.namespace,
        window:"Last 60 minutes by produced_at, within bounded source observations",
        clock:pipe.clock,source_bounds:pipe.bounds,latency:pipe.latency} : null,
      infrastructure:infra,definitions:{eventRate:"Events per completed event-time minute, up to latest five minutes; not processing capacity",
        retrievalP95:"Nearest-rank p95 of executed catalogue searches in latest 60 saved session turns, milliseconds",
        failures:"Dependency-error turns / saved turns (latest 500), percent",
        pipeline:"Event creation to active Gold; excludes HTTP before event creation and unresolved or unqualified timings",
        lag:"Sum of committed consumer lag across monitored group-partitions; unavailable if coverage is incomplete"}}};
  }
  root.DashboardPresentation={render,pipeline,stale,exportSnapshot};
  root.addEventListener("infrastructure-snapshot",e=>{infra=e.detail;staleSources.delete("infrastructure");cards();});
  document.addEventListener("DOMContentLoaded",cards);
})(typeof window==="object" ? window : globalThis);
