"use strict";

// Only explicit controls mutate. Loading, refresh, visibility and polling are reads.
(() => {
  const endpoint = "http://127.0.0.1:8010";
  const concepts = {
    analytics: ["Asynchronous isolation", "Checkout can finish while analytics processing is paused. Retained events catch up after recovery; the exact final order must match active Gold."],
    retry: ["Idempotency across an uncertain response", "The local gateway discards a real checkout acknowledgement after commit and returns an injected 504. Explicitly retry the original request ID, key and body; verify one purchase, debit and stock commitment."],
    decline: ["Saga compensation", "A run-scoped deterministic simulated decline must cancel the order, release its reservation and restore stock with zero signed net debit."],
    crash: ["Durable recovery after a committed effect", "Orders exits at saga.after_commit: Inventory has committed, but the saga has not saved its next step. Restart and verify that completed effects occur once."],
    refund: ["Debit followed by compensation", "A successful simulated payment creates one real debit. The scoped saga delay lets the reservation expire before stock commit; normal compensation must release stock and create exactly one matching reversal."],
    purchase: ["End-to-end observation", "One confirmed simulated purchase through the real services and active Gold."],
    late: ["Expiry and a delayed callback", "A persisted 35-second payment delay outlives the 30-second reservation. Current saga rules quiesce and cancel the pending callback, release stock and prevent a late debit. Manual review never passes."]
  };
  let connected=false,busy=false,current=null,poll,first=true;
  const requestedScenario=new URLSearchParams(location.search).get("scenario");
  if(requestedScenario && concepts[requestedScenario]) document.getElementById("failure-scenario").value=requestedScenario;
  const el=id=>document.getElementById(`failure-${id}`);
  const make=(tag,text="",cls="")=>{const e=document.createElement(tag);e.textContent=text;e.className=cls;return e;};
  const stamp=value=>new Date(value).toLocaleTimeString("en-IN",{hour12:false});
  const valueText=v=>v===null || v===undefined ? "Unavailable" : typeof v==="object" ? JSON.stringify(v) : String(v);
  const error=text=>{el("error").hidden=!text;el("error").textContent=text || "";};
  async function api(path,body) {
    const response=await fetch(endpoint+path,{method:body===undefined ? "GET" : "POST",headers:body===undefined ? {Accept:"application/json"} : {"Content-Type":"application/json"},
      body:body===undefined ? undefined : JSON.stringify(body),credentials:"omit",cache:"no-store",signal:AbortSignal.timeout(35000)});
    const result=await response.json();if(!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);return result;
  }
  function selection() {
    const scenario=el("scenario").value;if(scenario!=="analytics") el("mode").value="automated";
    el("mode").options[0].disabled=scenario!=="analytics";
    const automated=el("mode").value==="automated",[heading,description]=concepts[scenario];
    el("concept").replaceChildren(make("strong",heading),make("p",description));el("consent-label").hidden=!automated;
    el("preconditions").textContent=automated ? "Prepare selects one available product and captures owner stock. Review the product and check the consent box before triggering. No purchase occurs during Prepare." : "Add your product to the store cart first, then Prepare → Trigger. Place the order through normal store review and confirmation; return here to Watch it before recovery.";
    buttons();
  }
  function buttons() {
    const r=current?.run,live=r?.status==="Pending",selected=r && r.scenario===el("scenario").value && r.mode===el("mode").value;
    const ready=connected && !busy,automated=el("mode").value==="automated",consent=!automated || el("consent").checked;
    el("prepare").disabled=!ready || live || !!r?.fault_active;
    el("trigger").disabled=!ready || !selected || !live || r.triggered || !consent;
    el("test").disabled=!ready || !selected || !live || r.triggered || !automated || !consent;
    el("recover").disabled=!ready || !r || r.test_running || !live && !r.fault_active;
    el("retry").disabled=!ready || !live || !r?.response_lost || r.test_running || !r.checkout;
    el("verify").disabled=!ready || !live || !r?.triggered || r.test_running;
    el("watch").disabled=!ready || !live || !r?.triggered || r.mode!=="manual" || r.test_running;
    el("evidence").disabled=!connected || !r;el("scenario").disabled=busy || live;el("mode").disabled=busy || live;
  }
  function fact(label,value,cls="") {const e=make("div","",cls);e.append(make("span",label),make("strong",value));el("facts").append(e);}
  function render(data) {
    current=data;const r=data.run;
    el("connection").textContent=`Local controller connected · namespace ${data.namespace} · observed ${stamp(data.observed_at)} · independent 2-second sampling while active`;
    el("connect").textContent="Refresh controller";
    if(first && r){el("scenario").value=r.scenario;el("mode").value=r.mode;selection();}first=false;
    if(r){
      el("status").textContent=r.status;el("status").className=`badge ${r.status==="Passed" ? "" : "warning"} ${r.status==="Failed" ? "failed" : ""}`;
      el("run-title").textContent=data.scenarios[r.scenario];el("run-scope").textContent=`${r.mode==="manual" ? "LIVE MANUAL DEMO" : "AUTOMATED TEST · SCRIPTED SIMULATED PURCHASE"} · Run ${r.id} · ${r.completed_at ? "Completed "+stamp(r.completed_at)+" · retained evidence" : "Started "+stamp(r.started_at)}`;
      el("message").textContent=r.message;el("message").classList.toggle("failure-success",r.status==="Passed");
      const stages=["Prepare","Trigger","Observe","Recover","Verify"],reached=new Set(r.events.map(e=>e.phase));
      [...el("steps").children].forEach((li,i)=>{li.classList.toggle("reached",reached.has(stages[i]));li.classList.toggle("current",r.phase===stages[i]);});
      el("facts").replaceChildren();const s=r.samples.at(-1),p=r.publication;
      fact("Analytics worker",s?.worker_running===null || !s ? "Not measured" : s.worker_paused ? "Paused" : s.worker_running ? "Running" : "Stopped");
      fact("Analytics read API",s?.analytics_api_ready===true ? "Ready" : s?.analytics_api_ready===false ? "Unavailable" : "Not measured");
      fact("Order",r.order ? `${r.order.status} · v${r.order.order_version}` : r.checkpoint ? "Process stopped at checkpoint" : "Awaiting selection");
      fact("Exact Gold",p ? p.status==="visible" ? `Matched · generation ${p.generation}` : p.status : "Not measured");
      if(r.checkout) fact("Request / idempotency key",`${r.checkout.request_id} / ${r.checkout.key}`,"failure-wide mono");
      if(r.checkpoint) fact("Exercised checkpoint",`${r.checkpoint.checkpoint} · exit ${r.checkpoint.exit_code}`,"failure-wide");
      fact("Fault state",r.fault_active ? "Active · recovery required" : r.recovered ? "Recovered · controls cleared" : "Not armed");
      fact("Samples / bounds",`${r.samples.length} / ${r.limits.max_samples} · ${r.limits.run_seconds}s limit`);
      if(document.activeElement!==el("order-id") && r.order_id) el("order-id").value=r.order_id;
      el("prepared-product").hidden=!r.product;
      if(r.product) el("prepared-product").replaceChildren(make("strong",r.product.title),make("span",`${r.product.sku} · ${currency(r.product.price_minor)} · quantity 1`));
      el("checks").replaceChildren();if(!r.checks.length) el("checks").append(make("div","No verification result yet. Complete observation and recovery, then Verify.","empty"));
      for(const c of r.checks){const row=make("div","",`failure-check ${c.passed===true ? "pass" : c.passed===false ? "fail" : "pending"}`);row.append(make("span",c.passed===true ? "✓" : c.passed===false ? "×" : "○"),make("strong",c.name),make("small",`Expected ${valueText(c.expected)} · observed ${valueText(c.observed)}`));el("checks").append(row);}
      el("journal").replaceChildren();for(const e of r.events.slice(-30).reverse()){const row=make("li");row.append(make("time",stamp(e.at)),make("strong",e.phase),make("p",e.message));el("journal").append(row);}
      timeline(r);graphs(r);
    }
    el("history").replaceChildren();for(const previous of data.history.slice().reverse()){
      const row=make("tr");for(const v of [previous.id,data.scenarios[previous.scenario],previous.mode,previous.status]) row.append(make("td",v));
      const cell=make("td"),button=make("button","JSON ↓","button light");button.type="button";button.addEventListener("click",()=>download(previous.id));cell.append(button);row.append(cell);el("history").append(row);
    }buttons();
  }
  function timeline(r) {
    if(!r.samples.length){empty("failure-timeline","Waiting for the first timestamped observation.");return;}
    const graph=svg("svg",{viewBox:"0 0 620 205",role:"img","aria-label":"Timestamped observations of worker pause, analytics API readiness, terminal order and exact Gold match"});
    const start=new Date(r.started_at).getTime(),duration=Math.max(1,(new Date(r.samples.at(-1).at).getTime()-start)/1000),x=at=>111+(new Date(at).getTime()-start)/1000/duration*493;
    const lanes=[["Worker paused",s=>s.worker_paused,"#b28b3e"],["API ready",s=>s.analytics_api_ready,"#537f9d"],["Order terminal",s=>s.order_status===null ? null : ["CONFIRMED","CANCELLED","MANUAL_REVIEW"].includes(s.order_status),"#57795a"],["Gold matched",s=>s.gold_match,"#356b50"]];
    graph.append(svg("title",{},"Filled dots are observed true; pale dots observed false. Missing measurements have no dot. Hover for timestamps."));
    lanes.forEach(([label,read,colour],i)=>{const y=24+i*42;graph.append(svg("text",{x:0,y:y+3},label),svg("line",{x1:111,x2:604,y1:y,y2:y,stroke:"#edf0e8"}));
      for(const s of r.samples){const v=read(s);if(v===null || v===undefined) continue;const dot=svg("circle",{cx:x(s.at),cy:y,r:3.5,fill:v ? colour : "#d9e1d6"});dot.append(svg("title",{},`${stamp(s.at)} · ${label}: ${v} · ${s.order_status || "order unmeasured"}`));graph.append(dot);}});
    for(const ratio of [0,.5,1]) graph.append(svg("text",{x:111+493*ratio,y:194,"text-anchor":"middle"},`${Math.round(duration*ratio)}s`));el("timeline").replaceChildren(graph);
  }
  function measuredChart(target,points,series,caption) {
    const values=points.flatMap(p=>series.map(s=>p[s.key])).filter(v=>v!==null && v!==undefined);
    if(!values.length){empty(target,"No independent measurements yet.");return;}
    const graph=svg("svg",{viewBox:"0 0 620 205",role:"img","aria-label":caption});graph.append(svg("title",{},caption));
    const min=Math.min(0,...values),max=Math.max(1,...values),range=max-min,start=new Date(points[0].at).getTime(),duration=Math.max(1,new Date(points.at(-1).at).getTime()-start);
    const x=p=>42+(new Date(p.at).getTime()-start)/duration*562,y=v=>174-(v-min)/range*160;
    for(let i=0;i<=4;i++){const v=min+range*i/4;graph.append(svg("line",{x1:42,x2:605,y1:y(v),y2:y(v),stroke:"#e9ede5","stroke-dasharray":"3 4"}),svg("text",{x:35,y:y(v)+3,"text-anchor":"end"},v.toLocaleString("en-IN",{maximumFractionDigits:1})));}
    for(const s of series){let segment=[];const draw=()=>{if(segment.length>1) graph.append(svg("polyline",{points:segment.join(" "),fill:"none",stroke:s.colour,"stroke-width":2}));segment=[];};
      for(const p of points){const v=p[s.key];if(v===null || v===undefined){draw();continue;}segment.push(`${x(p)},${y(v)}`);const dot=svg("circle",{cx:x(p),cy:y(v),r:3,fill:s.colour});dot.append(svg("title",{},`${stamp(p.at)} · ${s.label}: ${v}`));graph.append(dot);}draw();}
    for(const ratio of [0,.5,1]) graph.append(svg("text",{x:42+562*ratio,y:198,"text-anchor":"middle"},`${Math.round(duration*ratio/1000)}s`));$(target).replaceChildren(graph);
  }
  function graphs(r) {
    const baseline=Object.values(r.baseline_stock),total=baseline.reduce((n,s)=>n+s.on_hand,0),reserved=baseline.reduce((n,s)=>n+s.reserved,0);
    const points=r.samples.map(s=>({...s,consumed:s.stock_on_hand===null ? null : total-s.stock_on_hand,reserved:s.stock_reserved===null ? null : s.stock_reserved-reserved,ledger:s.net_ledger_minor===null ? null : s.net_ledger_minor/100}));
    measuredChart("failure-stock-chart",points,[{key:"consumed",label:"Consumed stock",colour:"#356b50"},{key:"reserved",label:"Reserved stock",colour:"#bb964c"}],"Measured stock consumption and reservation change relative to baseline; elapsed seconds");
    measuredChart("failure-ledger-chart",points,[{key:"ledger",label:"Signed net ledger INR",colour:"#537f9d"}],"Independent signed payment ledger in INR; elapsed seconds");
  }
  async function refreshController() {
    clearTimeout(poll);try{const data=await api("/state");connected=true;render(data);}catch(e){connected=false;el("connection").textContent=`Controller unavailable. Displayed evidence is stale. ${e.message}`;buttons();}finally{if(connected && !document.hidden) poll=setTimeout(refreshController,2500);}
  }
  async function act(action) {
    if(busy)return;busy=true;buttons();error("");try{
      let result;if(action==="prepare"){
        const saved=JSON.parse(localStorage.getItem("shoptalk-session") || "{}"),body={scenario:el("scenario").value,mode:el("mode").value};
        if(body.mode==="manual")for(const k of ["session_id","run_id","user_id","correlation_id"])body[k]=saved[k];
        result=await api("/prepare",body);el("consent").checked=false;el("order-id").value="";
      }else if(action==="watch"){
        const saved=JSON.parse(localStorage.getItem("shoptalk-session") || "{}"),order=el("order-id").value.trim() || saved.order_id;
        if(!/^[0-9a-f-]{36}$/i.test(order || ""))throw new Error("Place a new order in the store, then enter its order ID.");result=await api(`/runs/${current.run.id}/watch/${order}`,{});
      }else result=await api(`/runs/${current.run.id}/${action}`,{confirmed:el("consent").checked});render(result);
    }catch(e){error(e.message);await refreshController();}finally{busy=false;buttons();}
  }
  async function download(id) {
    try{const response=await fetch(`${endpoint}/evidence/${id}`,{cache:"no-store",credentials:"omit",signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error("Evidence download unavailable");const url=URL.createObjectURL(await response.blob()),a=make("a");a.href=url;a.download=`failure-demo-${id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){error(e.message);}
  }
  el("connect").addEventListener("click",refreshController);for(const id of ["prepare","trigger","recover","retry","verify","watch","test"])el(id).addEventListener("click",()=>act(id));
  el("evidence").addEventListener("click",()=>download(current.run.id));el("scenario").addEventListener("change",selection);el("mode").addEventListener("change",selection);el("consent").addEventListener("change",buttons);
  document.addEventListener("visibilitychange",()=>{clearTimeout(poll);if(connected && !document.hidden)refreshController();});
  window.addEventListener("storage",event=>{if(event.key==="shoptalk-session" && current?.run?.mode==="manual" && document.activeElement!==el("order-id")){try{const id=JSON.parse(event.newValue || "{}").order_id;if(id && !current.run.baseline_orders.includes(id))el("order-id").value=id;}catch{/* wait for input */}}});selection();
})();
