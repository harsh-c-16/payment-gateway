"use strict";

const $ = id => document.getElementById(id);
const node = (tag, value = "", className = "") => {
  const n = document.createElement(tag); n.textContent = value; n.className = className; return n;
};
const fmt = value => value === null || value === undefined ? "Unavailable" : Number(value).toLocaleString("en-IN");
const ms = value => value === null || value === undefined ? "No samples" : `${fmt(Math.round(value))} ms`;
const localTime = value => new Date(value).toLocaleTimeString("en-IN", {hour:"2-digit",minute:"2-digit",second:"2-digit"});
const currency = value => new Intl.NumberFormat("en-IN", {style:"currency",currency:"INR",maximumFractionDigits:0}).format(value/100);
const title = value => String(value).replaceAll("_"," ").toLowerCase().replace(/\b\w/g, c=>c.toUpperCase());
let S = {}, lastSnapshot = null, timer, paused = false, refreshing = false;
function readState() { try {return JSON.parse(localStorage.getItem("shoptalk-session")) || {};} catch {return {};} }
const headers = () => ({"Accept":"application/json","Content-Type":"application/json", "X-Namespace":S.namespace,
  "X-User-ID":S.user_id,"X-Run-ID":S.run_id,"X-Correlation-ID":S.correlation_id,
  "X-Session-ID":S.session_id,"X-Request-ID":crypto.randomUUID()});
async function request(path, options = {}) {
  const response = await fetch(path, {...options,headers:options.headers || headers(),
    cache:"no-store",credentials:"omit",signal:AbortSignal.timeout(12000)});
  if (!response.ok) throw new Error(`Dashboard request failed (${response.status}).`);
  return response.json();
}
function empty(target, message = "No observations yet. Use the store to generate activity.") {
  $(target).replaceChildren(node("div",message,"empty"));
}
function statList(target, values) {
  $(target).replaceChildren();
  for(const [label,value] of values) {
    const n=node("div",label); n.append(node("strong",value)); $(target).append(n);
  }
}
function bars(target, values, unavailable = false, limit = 8) {
  const entries=Object.entries(values || {}).sort((a,b)=>b[1]-a[1]);
  if(unavailable || entries.length===0) {empty(target,unavailable ? "This data source is unavailable." : "No published observations in this window.");return;}
  const max=Math.max(1,...entries.map(([,v])=>v)); $(target).replaceChildren();
  for(const [label,value] of entries.slice(0,limit)) {
    const row=node("div","","bar-row"), labelRow=node("div","","bar-label");
    labelRow.append(node("span",title(label)),node("strong",fmt(value)));
    const track=node("div","","bar-track"), graph=svg("svg",{viewBox:"0 0 100 6",preserveAspectRatio:"none","aria-hidden":"true"});
    graph.append(svg("rect",{x:0,y:0,width:value/max*100,height:6,rx:3,fill:"#648568"}));
    track.append(graph);row.append(labelRow,track);$(target).append(row);
  }
  if(entries.length>limit) $(target).append(node("p",`+ ${entries.length-limit} more types · export for the full breakdown`,"bar-tail"));
}
function svg(tag, attributes = {}, text) {
  const n=document.createElementNS("http://www.w3.org/2000/svg",tag);
  for(const [k,v] of Object.entries(attributes)) n.setAttribute(k,String(v));
  if(text !== undefined) n.textContent=text; return n;
}
function lineChart(target, points, series, caption, xLabel) {
  if(points === null) {empty(target,"This data source is unavailable.");return;}
  if(!points.length) {empty(target);return;}
  const width=620,height=205,left=42,right=12,top=12,bottom=30;
  const plotW=width-left-right,plotH=height-top-bottom;
  const rawMax=Math.max(4,...points.flatMap(p=>series.map(s=>p[s.key] ?? 0)));
  const step=10 ** Math.floor(Math.log10(rawMax)); const max=Math.ceil(rawMax/step)*step;
  const graph=svg("svg",{viewBox:`0 0 ${width} ${height}`,role:"img","aria-label":caption});
  graph.append(svg("title",{},caption));
  for(let i=0;i<=4;i++) {
    const y=top+plotH-i*plotH/4;
    graph.append(svg("line",{x1:left,y1:y,x2:width-right,y2:y,stroke:"#e9ede5","stroke-dasharray":"3 4"}));
    graph.append(svg("text",{x:left-8,y:y+3,"text-anchor":"end"},Math.round(max*i/4).toLocaleString("en-IN")));
  }
  const x=i=>left+(points.length===1 ? plotW/2 : i*plotW/(points.length-1));
  for(const s of series) {
    let segment=[];
    const draw=()=>{if(segment.length>1) graph.append(svg("polyline",{points:segment.join(" "),fill:"none",stroke:s.colour,"stroke-width":2.5,"stroke-linejoin":"round"}));segment=[];};
    points.forEach((p,i)=>{
      if(p[s.key] === null || p[s.key] === undefined) {draw();return;}
      const y=top+plotH-(p[s.key]/max*plotH);segment.push(`${x(i)},${y}`);
      const dot=svg("circle",{cx:x(i),cy:y,r:points.length>20 ? 1.5 : 3,fill:s.colour});
      dot.append(svg("title",{},`${xLabel(p,i)} · ${s.label}: ${fmt(Math.round(p[s.key]))}`));graph.append(dot);
    });draw();
  }
  const ticks=[...new Set([0,Math.floor((points.length-1)/2),points.length-1])];
  for(const i of ticks) graph.append(svg("text",{x:x(i),y:height-7,"text-anchor":"middle"},xLabel(points[i],i)));
  $(target).replaceChildren(graph);
}
function renderDetailed(data) {
 const m=data.session,p=data.pipeline,a=data.activity;
  bars("event-types",p?.by_type,!p);bars("event-services",p?.by_service,!p);
  lineChart("latency-chart",a.turns,[{key:"total_ms",colour:"#356b50",label:"Total ms"},{key:"model_ms",colour:"#c89c4e",label:"Model ms"}],
    "Measured total and model response time for saved session turns",(point,i)=>`Turn ${Math.max(0,m.sampled_turns-a.turns.length)+i+1}`);
  statList("session-stats",[["Saved turns",fmt(m.sampled_turns)],["Chat searches",fmt(m.searches)],
    ["Model attempts · whole session",fmt(m.model_attempts)],["Query embeddings",fmt(m.query_embeddings)],
    ["Turn P50",ms(m.turn_p50_ms)],["Mean model time",ms(m.model_mean_ms)],["Dependency errors",fmt(m.dependency_errors)]]);
  bars("order-statuses",data.orders?.by_status,!data.orders);
  statList("order-stats",[["Published orders",data.orders ? fmt(data.orders.count) : "Unavailable"],
    ["Confirmed demo value",data.orders ? currency(data.orders.confirmed_minor) : "Unavailable"]]);
  const receipts=data.receipt_sample;
  bars("receipt-dispositions",receipts ? {new_valid:0,duplicate_delivery:0,invalid:0,redelivery_noop:0,...receipts.dispositions} : null,!receipts);
  $("receipt-scope").textContent=receipts ? `${fmt(receipts.count)} unique source positions from ${fmt(receipts.journal_observations)} journal observations · ${receipts.complete ? "journal exhausted at read" : `first ${receipts.limit}; additional observations may exist`}` : "Receipt sample is unavailable";
  $("receipt-latency").textContent=receipts ? `Observed ingest → Gold P95: ${ms(receipts.visibility_p95_ms)} · ${fmt(receipts.observed_timings)} valid samples. Recovery bounds and missing timings are excluded.` : "No receipt latency measurements are available.";
  $("receipts").replaceChildren();
  if(!receipts?.rows.length) {
    const row=node("tr"),cell=node("td",receipts ? "No source receipts yet." : "Receipt source unavailable.");cell.colSpan=6;row.append(cell);$("receipts").append(row);
  }
  for(const r of receipts?.rows || []) {
    const row=node("tr"),source=r.source;
    for(const [i,value] of [(r.event_id || "No valid event ID").slice(0,14),source.topic || source.kind || "File source",
      source.partition !== undefined ? `${source.partition} : ${source.offset}` : "Not a Kafka source",
      title(r.disposition),r.gold_visible ? "Yes" : "Pending",ms(r.visibility_ms)].entries()) {
      const cell=node("td",value,i<3 ? "mono" : "");row.append(cell);
    }
    $("receipts").append(row);
  }
  $("datasets").replaceChildren();$("positions").replaceChildren();
  for(const dataset of ["silver","gold"]) {
    const d=data.datasets.find(d=>d.dataset===dataset),card=node("div","","dataset");
    const heading=node("h4",title(dataset));heading.append(node("span",d ? `Generation ${fmt(d.generation)}` : "Unavailable"));card.append(heading);
    if(d) {
      const facts=node("dl");
      for(const [label,value] of [["Files",fmt(d.files)],["Physical rows",fmt(d.rows)],["Stored size",`${(d.bytes/1048576).toFixed(2)} MiB`],["Source partitions",fmt(d.partitions)]]) facts.append(node("dt",label),node("dd",value));
      card.append(facts,node("p",`Published ${new Date(d.created_at).toLocaleString()} · ${d.transform_version}`));
      for(const position of d.positions) {
        const row=node("tr");for(const value of [title(dataset),position.topic,position.partition,position.next_offset]) row.append(node("td",String(value)));$("positions").append(row);
      }
    } else card.append(node("p","No active manifest could be read."));
    $("datasets").append(card);
  }
  const c=data.catalogue;$("catalogue").replaceChildren();
  if(c) {
    $("catalogue").append(node("p",c.hybrid_ready===null ? "Retriever availability unknown" : c.hybrid_ready ? "Hybrid retrieval ready" : "Hybrid retrieval unavailable",`badge ${c.hybrid_ready ? "" : "warning"}`));
    const facts=node("dl","","facts");for(const [label,value] of [["Category roots",c.categories],["Recorded brands",c.brands],["Colour values",c.colours],["Material values",c.materials]]) facts.append(node("dt",label),node("dd",fmt(value)));
    $("catalogue").append(facts,node("p",`Dataset revision: ${c.dataset_revision}`,"footnote"),
      node("p","Product types and hard filters apply before hybrid ranking. Missing attributes remain unknown.","footnote"));
    const coverage={};
    for(const category of Object.values(c.coverage_by_category)) for(const [k,v] of Object.entries(category)) coverage[k]=(coverage[k] || 0)+v;
    $("coverage").replaceChildren();
    $("coverage-note").textContent=`${fmt(coverage.canonical)} canonical listings · ${fmt(coverage.active)} active/priced · counts from the imported facet dictionary`;
    for(const field of ["brand","colour","material","size"]) {
      const count=coverage[field] ?? 0,total=coverage.canonical ?? 0;
      const card=node("div","","coverage-card"),labels=node("div","","bar-label");
      const percent=total ? count/total*100 : 0;
      labels.append(node("span",title(field)),node("strong",total ? percent>0 && percent<.1 ? "<0.1%" : `${percent.toFixed(1)}%` : "No samples"));
      const graph=svg("svg",{viewBox:"0 0 100 8",preserveAspectRatio:"none",role:"img","aria-label":`${field}: ${count} of ${total} canonical listings recorded`});
      graph.append(svg("rect",{width:100,height:8,rx:4,fill:"#e9ede4"}),svg("rect",{width:total ? count/total*100 : 0,height:8,rx:4,fill:"#648568"}));
      card.append(labels,graph,node("p",`${fmt(count)} recorded · ${fmt(Math.max(0,total-count))} missing`,"footnote"));$("coverage").append(card);
    }
  } else {empty("catalogue","Catalogue metadata is unavailable.");empty("coverage","Catalogue coverage is unavailable.");}
}
function render(data) {
  renderDetailed(data);
  const m=data.session,p=data.pipeline,ready=data.services.filter(s=>s.status==="ready").length;
  $("namespace").textContent=`Dataset: ${data.namespace}`;
  $("session-scope").textContent=`Chat: ${m.sampled_turns} saved messages in this session`;
  $("date-scope").textContent=`Activity: ${data.pipeline_date_utc} UTC`;
  $("kpis").replaceChildren();
  for(const [label,value] of [["Events in analytics",p ? fmt(p.events) : "Unavailable"],["Orders today",data.orders ? fmt(data.orders.count) : "Unavailable"],["Chat response p95",ms(m.turn_p95_ms)],["Services ready",`${ready} / ${data.services.length}`]]) {
    const card=node("article","","kpi");card.append(node("span",label,"label"),node("strong",value));$("kpis").append(card);
  }
  $("services").replaceChildren();
  for(const service of data.services) {const row=node("div","",`service ${service.status}`);row.append(node("span","","indicator"),document.createTextNode(title(service.name)),node("small",service.status==="ready" ? "Ready" : "Unavailable"));$("services").append(row);}
  lineChart("throughput-chart",p?.minutes ?? null,[{key:"events",colour:"#356b50",label:"Events"}],"Unique events by event-time minute",point=>new Date(point.minute).toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit",timeZone:"UTC"}));
  $("throughput-note").textContent=p ? `Gold version ${fmt(p.generation)}. Late events can update an earlier minute.` : "Analytics is unavailable.";
  bars("order-statuses",data.orders?.by_status,!data.orders);
  statList("order-stats",[["Confirmed order value",data.orders ? currency(data.orders.confirmed_minor) : "Unavailable"]]);
  $("updated").textContent=`Updated ${localTime(data.checked_at)}`;
  const partial=data.unavailable.length>0 || ready<data.services.length;
  $("live-status").textContent=paused ? "Paused" : partial ? "Some data unavailable" : "Live";
  $("live-status").classList.toggle("warning",partial || paused);
  $("error").hidden=!partial;$("error").textContent=partial ? "Some services could not be read. Available readings are shown below." : "";
}
async function watchedOrder() {
  $("watched-order").replaceChildren();
  if(!S.order_id) {empty("watched-order","No order yet. Place a demo order in the store to follow it here.");return;}
  try {
    const [order,publication]=await Promise.all([request(`/v1/store/orders/${S.order_id}`),request(`/v1/store/orders/${S.order_id}/pipeline`)]);
    const match=publication.status==="visible" && publication.order_version===order.order_version;
    $("watched-order").append(node("strong",title(order.status)),node("p",`Order ${order.order_id}`,"mono"),
      node("span",match ? `Matched in Gold · generation ${publication.generation}` : publication.status==="unavailable" ? "Analytics unavailable" : "Waiting for matching Gold version",`tag ${match ? "" : "warning"}`),
      node("p",`Order version ${order.order_version} · ${currency(order.total_amount_minor)}`),
      node("p",""));
  } catch {empty("watched-order","Order status is unavailable. No purchase was resubmitted.");}
}
async function refresh() {
  clearTimeout(timer);if(refreshing) return;
  const current=readState();
  if(current.session_id && current.namespace===S.namespace) S=current;
  refreshing=true;$("refresh").disabled=true;
  try {
    const data=await request(`/v1/sessions/${S.session_id}/dashboard`);
    lastSnapshot=data;render(data);$("export").disabled=false;
    await watchedOrder();
  } catch(e) {
    $("error").hidden=false;$("error").textContent=`Could not refresh. ${lastSnapshot ? "Displayed charts are stale; their timestamp is retained. " : "No snapshot is available yet. "}${e.message}`;
    $("live-status").textContent="Unavailable";$("live-status").classList.add("warning");
  } finally {
    refreshing=false;$("refresh").disabled=false;
    if(!paused && !document.hidden) timer=setTimeout(refresh,5000);
  }
}
async function boot() {
  const config=await request("/v1/store/bootstrap",{headers:{Accept:"application/json"}});
  S=readState();
  if(S.namespace && S.namespace!==config.namespace) throw new Error("Your saved session belongs to another deployment. Open this deployment in a separate browser profile.");
  if(!S.session_id) {
    if(S.pending) throw new Error("Finish the saved request in the store before opening the dashboard.");
    S.namespace=config.namespace;S.user_id ||= "shopper-"+crypto.randomUUID();S.run_id ||= crypto.randomUUID();S.correlation_id ||= crypto.randomUUID();
    const operation={label:"session",path:"/v1/sessions",method:"POST",body:{},headers:{...headers(),"Idempotency-Key":crypto.randomUUID()}};
    delete operation.headers["X-Session-ID"];
    S.pending=operation;localStorage.setItem("shoptalk-session",JSON.stringify(S));
    const created=await request(operation.path,{...operation,body:JSON.stringify(operation.body)});
    S.session_id=created.session_id;S.cart_id=created.cart_id;delete S.pending;
    localStorage.setItem("shoptalk-session",JSON.stringify(S));
  }
  await refresh();
}
$("refresh").addEventListener("click",()=>{if(S.session_id) refresh();else boot().catch(showBootError);});
$("pause").addEventListener("click",()=>{
  paused=!paused;clearTimeout(timer);$("pause").textContent=paused ? "Resume" : "Pause";
  window.dashboardObservationPaused=paused;
  window.dispatchEvent(new CustomEvent("observation-pause",{detail:{paused}}));
  if(paused) {$("live-status").textContent="Paused";$("live-status").classList.add("warning");}
  else if(S.session_id) refresh();
});
$("refresh").addEventListener("click",()=>window.dispatchEvent(new CustomEvent("observation-refresh")));
$("export").addEventListener("click",()=>{
  if(!lastSnapshot) return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(lastSnapshot,null,2)],{type:"application/json"}));
  const a=node("a");a.href=url;a.download=`shoptalk-dashboard-${lastSnapshot.pipeline_date_utc}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
document.addEventListener("visibilitychange",()=>{clearTimeout(timer);if(!document.hidden && !paused && S.session_id) refresh();});
window.addEventListener("storage",e=>{if(e.key==="shoptalk-session" && !document.hidden && !paused && S.session_id) refresh();});
function showBootError(e) {$("error").hidden=false;$("error").textContent=e.message;$("live-status").textContent="Unavailable";}
boot().catch(showBootError);
