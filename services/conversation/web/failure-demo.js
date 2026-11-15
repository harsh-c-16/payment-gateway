"use strict";

// Only explicit controls mutate. Loading, refresh, visibility and polling are reads.
(() => {
  const endpoint = "http://127.0.0.1:8010";
  const concepts = {
    analytics: ["Asynchronous isolation", "Checkout can finish while analytics processing is paused. Retained events catch up after recovery; the exact final order must match active Gold."],
    retry: ["Idempotency across an uncertain response", "The local gateway discards a real checkout acknowledgement after commit and returns an injected 504. Explicitly retry the original request ID, key and body; verify one purchase, debit and stock commitment."],
    decline: ["Saga compensation", "A run-scoped deterministic simulated decline must cancel the order, release its reservation and restore stock with zero signed net debit."],
    crash: ["Durable recovery after a committed effect", "Orders exits at saga.after_commit: Inventory has committed, but the saga has not saved its next step. Restart and verify that completed effects occur once."],
    refund: ["Debit followed by compensation", "A successful simulated payment creates one ledger debit. The scoped saga delay lets the reservation expire before stock commit; normal compensation must release stock and create exactly one matching reversal."],
    purchase: ["End-to-end observation", "One confirmed simulated purchase through the real services and active Gold."],
    late: ["Expiry and a delayed callback", "A persisted 35-second payment delay outlives the 30-second reservation. Current saga rules quiesce and cancel the pending callback, release stock and prevent a late debit. Manual review never passes."]
  };
  const descriptions={
    analytics:"Pause analytics, place a test order, then check that analytics catches up.",
    retry:"Retry the same checkout and check that only one order and payment are created.",
    decline:"Decline the payment and check that the order is cancelled and stock is restored.",
    crash:"Stop order processing, restart it and check that the order recovers correctly.",
    late:"Delay payment beyond the stock reservation and check that the order cancels safely.",
    refund:"Debit a simulated payment, then check that it is reversed and stock is restored."
  };
  let connected=false,busy=false,current=null,poll,first=true,logSignature="";
  const requestedScenario=new URLSearchParams(location.search).get("scenario");
  if(requestedScenario && concepts[requestedScenario]) document.getElementById("failure-scenario").value=requestedScenario;
  const el=id=>document.getElementById(`failure-${id}`);
  const make=(tag,text="",cls="")=>{const e=document.createElement(tag);e.textContent=text;e.className=cls;return e;};
  const stamp=value=>new Date(value).toLocaleTimeString("en-IN",{hour12:false});
  const valueText=v=>v===null || v===undefined ? "Unavailable" : typeof v==="object" ? JSON.stringify(v) : String(v);
  function checkValue(value,name) {
    if(value===null || value===undefined)return "Unavailable";
    if(typeof value==="number" && /amount/i.test(name))return `INR ${(value/100).toFixed(2)}`;
    if(Array.isArray(value))return `${value.length} record${value.length===1 ? "" : "s"}`;
    if(typeof value==="object")return "Recorded fields (expand below)";
    if(typeof value==="string" && /^[0-9a-f-]{36}$/i.test(value))return value.slice(0,8)+"…";
    return valueText(value);
  }
  const error=text=>{el("error").hidden=!text;el("error").textContent=text || "";};
  async function api(path,body) {
    const response=await fetch(endpoint+path,{method:body===undefined ? "GET" : "POST",headers:body===undefined ? {Accept:"application/json"} : {"Content-Type":"application/json"},
      body:body===undefined ? undefined : JSON.stringify(body),credentials:"omit",cache:"no-store",signal:AbortSignal.timeout(35000)});
    const result=await response.json();if(!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);return result;
  }
  function selection() {
    const scenario=el("scenario").value;if(scenario!=="analytics") el("mode").value="automated";
    el("mode").querySelector('option[value="manual"]').disabled=scenario!=="analytics";
    const automated=el("mode").value==="automated";
    el("concept").replaceChildren(make("p",!automated ? "Add an item to your store cart, then prepare the test and place the order yourself." : descriptions[scenario]));el("consent-label").hidden=!automated;
    el("preconditions").textContent=automated ? "Approve one simulated checkout, then click Prepare test. It captures the baseline, injects the fault, runs the checkout and verifies recovery automatically." : "Add a product to the store cart, then click Prepare test to capture its baseline and pause analytics. Place the order through normal store confirmation, then watch it here before resuming processing.";
    el("consent").checked=false;error("");buttons();
  }
  function buttons() {
    const r=current?.run,live=r?.status==="Pending",selected=r && r.scenario===el("scenario").value && r.mode===el("mode").value;
    const ready=connected && !busy,automated=el("mode").value==="automated",consent=!automated || el("consent").checked;
    el("prepare").disabled=!ready || !consent || !!r?.fault_active || !!r?.test_running || !!live && (!selected || !!r.triggered);
    el("prepare").textContent=busy ? "Preparing and starting..." : live && (r.triggered || r.test_running) ? "Test running..." : "Prepare test";
    el("recover").disabled=!ready || !r || r.test_running || !live && !r.fault_active;
    el("retry").disabled=!ready || !live || !r?.response_lost || r.test_running || !r.checkout;
    el("verify").disabled=!ready || !live || !r?.triggered || r.test_running;
    el("watch").disabled=!ready || !live || !r?.triggered || r.mode!=="manual" || r.test_running;
    el("recover").hidden=!!r?.test_running || !r?.fault_active && (!live || !r?.triggered || !!r?.recovered);
    el("verify").hidden=!live || !r?.triggered || !!r?.fault_active || !!r?.test_running;
    el("retry").hidden=!live || !r?.response_lost || !!r?.test_running;
    el("watch").closest(".failure-watch").hidden=automated || !live || !r?.triggered;
    el("consent-label").hidden=!automated;
    el("consent").disabled=busy || !!r?.test_running || !!live && !!r.triggered;
    el("preconditions").hidden=true;
    el("next").hidden=connected && !busy && !live && !r?.fault_active;
    el("next").textContent=!connected ? "Connecting automatically. Test controls become available when the local helper is ready." : busy ? "Waiting for the controller..." : r?.test_running ? "Test running. Follow the log below." : r?.fault_active && !live ? "The run has ended with a fault still active. Resume processing to clear it before another test." : !live ? (automated ? "Approve one simulated checkout and click Prepare test. Baseline capture, fault injection, checkout and recovery run automatically." : "Click Prepare test to capture the cart baseline and pause analytics. Then place one order in the store.") : !r.triggered ? automated ? "This test has a saved baseline. Approve one simulated checkout and click Prepare test to continue it." : "Click Prepare test to pause analytics, then place one order in the store." : !automated && !r.order_id ? "Place the order in the store, then click Watch order. The saved order ID is used automatically; enter an ID only if needed." : r.fault_active ? "Inspect the order and Gold state, then resume processing." : "Processing is restored. Click Verify recovery to reconcile the order, stock, ledger and active Gold.";
    const workspace=el("run-title").closest(".failure-workspace");workspace.hidden=!selected;
    workspace.querySelector('a[href="/"]').hidden=automated;
    el("observations").hidden=!selected;
    el("prepared-product").hidden=!selected || !live || !r?.product;
    renderEvidence(selected ? r : null);
    el("evidence").disabled=!connected || !r;el("scenario").disabled=busy || live;el("mode").disabled=busy || live;
  }
  function fact(label,value,cls="") {const e=make("div","",cls);e.append(make("span",label),make("strong",value));el("facts").append(e);}
  function renderEvidence(run) {
    const rows=window.FailureEvidence.presentationLog(run),signature=JSON.stringify([run?.id,rows]);
    el("log-scope").textContent=run ? `${run.status==="Pending" ? "Live test" : "Saved test result"} · ${rows.length} meaningful changes · local time. API states are sampled; intermediate states may be missed. Expand a row for identifiers.` : "Run a test to see the fault, order transitions, compensation and Gold reconciliation.";
    if(signature!==logSignature){
      const log=el("journal"),bottom=log.scrollHeight-log.scrollTop-log.clientHeight<40,top=log.scrollTop;
      const opened=new Set([...log.querySelectorAll("details[open]")].map(d=>d.dataset.entryId));
      log.replaceChildren();
      if(!run)log.append(make("li","Choose a scenario and click Prepare test. No fault or purchase has been submitted.","empty"));
      for(const row of rows){
        const li=make("li","",`execution-entry ${row.basis}`),time=make("time",Number.isFinite(Date.parse(row.at)) ? stamp(row.at) : "No time");
        if(row.at){time.dateTime=row.at;time.title=new Date(row.at).toISOString();}
        li.append(time,make("strong",row.source),make("span",row.message));
        const detailKeys=Object.keys(row.details).filter(k=>row.details[k]!==undefined && row.details[k]!==null);
        if(detailKeys.length || row.basis==="service_record"){
          const detail=make("details"),key=`${row.at}/${row.source}/${row.message}`;detail.dataset.entryId=key;detail.open=opened.has(key);
          detail.append(make("summary",row.basis==="service_record" ? "Ledger / checkpoint evidence" : "Technical details"),make("pre",JSON.stringify(row.details,null,2)));li.append(detail);
        }
        log.append(li);
      }
      if(bottom && run?.status==="Pending")log.scrollTop=log.scrollHeight;
      else log.scrollTop=signature!==logSignature && !logSignature ? 0 : top;
      logSignature=signature;
    }
    el("checks").replaceChildren();
    if(!run?.checks?.length)el("checks").append(make("div",run?.status==="Pending" ? "Waiting for observation and recovery. Checks will compare the actual order, stock, ledger and Gold with the expected result." : "Checks appear after the selected test runs.","empty"));
    for(const c of run?.checks || []){
      const row=make("div","",`failure-check ${c.passed===true ? "pass" : c.passed===false ? "fail" : "pending"}`);
      const expected=checkValue(c.expected,c.name),observed=checkValue(c.observed,c.name);
      row.append(make("span",c.passed===true ? "PASS" : c.passed===false ? "FAIL" : "WAIT"),make("strong",c.name),make("small",`Expected ${expected} / observed ${observed}`));
      if(expected!==valueText(c.expected) || observed!==valueText(c.observed)){
        const detail=make("details");detail.append(make("summary","Exact values"),make("pre",JSON.stringify({expected:c.expected,observed:c.observed},null,2)));row.append(detail);
      }
      el("checks").append(row);
    }
  }
  function render(data) {
    current=data;const r=data.run;
    el("connection").textContent=`Local controller connected · namespace ${data.namespace} · observed ${stamp(data.observed_at)} · independent 2-second sampling while active`;
    el("connect").textContent="Refresh controller";
    if(first && r && (!requestedScenario || r.status==="Pending" || r.fault_active)){el("scenario").value=r.scenario;el("mode").value=r.mode;selection();}first=false;
    if(r){
      el("status").textContent=r.status;el("status").className=`badge ${r.status==="Passed" ? "" : "warning"} ${r.status==="Failed" ? "failed" : ""}`;
      el("run-title").textContent=data.scenarios[r.scenario];el("run-scope").textContent=`${r.mode==="manual" ? "Manual store checkout" : "Automated simulated order"} · ${r.completed_at ? "Saved result · "+new Date(r.completed_at).toLocaleString() : "Started "+stamp(r.started_at)}`;el("run-scope").title=`Run ${r.id}`;
      el("message").textContent=r.message;el("message").classList.toggle("failure-success",r.status==="Passed");
      const stages=["Prepare","Trigger","Observe","Recover","Verify"],reached=new Set(r.events.map(e=>e.phase));
      [...el("steps").children].forEach((li,i)=>{li.classList.toggle("reached",reached.has(stages[i]));li.classList.toggle("current",r.phase===stages[i]);});
      el("facts").replaceChildren();const s=r.samples.at(-1),p=r.publication;
      fact("Analytics worker",s?.worker_running===null || !s ? "Not measured" : s.worker_paused ? "Paused" : s.worker_running ? "Running" : "Stopped");
      fact("Analytics read API",s?.analytics_api_ready===true ? "Ready" : s?.analytics_api_ready===false ? "Unavailable" : "Not measured");
      fact("Order",r.order ? `${r.order.status} · v${r.order.order_version}` : r.checkpoint ? "Process stopped at checkpoint" : "Awaiting selection");
      fact("Exact Gold",p ? p.status==="visible" ? `Matched · generation ${p.generation}` : p.status : "Not measured");
      if(r.checkpoint) fact("Exercised checkpoint",`${r.checkpoint.checkpoint} · exit ${r.checkpoint.exit_code}`,"failure-wide");
      fact("Fault state",r.fault_active ? "Active · recovery required" : r.recovered ? "Recovered · controls cleared" : "Not armed");
      if(document.activeElement!==el("order-id") && r.order_id) el("order-id").value=r.order_id;
      el("prepared-product").hidden=!r.product;
      if(r.product) el("prepared-product").replaceChildren(make("strong",r.product.title),make("span",`${r.product.sku} · ${currency(r.product.price_minor)} · quantity 1`));
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
    clearTimeout(poll);try{const data=await api("/state");connected=true;render(data);}catch(e){connected=false;el("connection").textContent=current ? "Controller disconnected. Showing the last observation; reconnecting automatically." : "Connecting to the local controller. If it stays offline, run .\\start-failure-demo.ps1.";buttons();}finally{if(!document.hidden) poll=setTimeout(refreshController,connected ? 2500 : 5000);}
  }
  async function act(action) {
    if(busy)return;busy=true;buttons();error("");try{
      let result;if(action==="prepare"){
        const saved=JSON.parse(localStorage.getItem("shoptalk-session") || "{}"),body={scenario:el("scenario").value,mode:el("mode").value};
        if(body.mode==="manual")for(const k of ["session_id","run_id","user_id","correlation_id"])body[k]=saved[k];
        const approved=body.mode==="manual" || el("consent").checked;
        if(!approved)throw new Error("Approve one simulated checkout before starting the test.");
        const pending=current?.run;
        if(pending?.status==="Pending"){
          if(pending.scenario!==body.scenario || pending.mode!==body.mode || pending.triggered || pending.test_running)throw new Error("The current test is already running or requires recovery.");
          result=current;
        }else result=await api("/prepare",body);
        const run=result.run;render(result);el("order-id").value="";
        result=await api(`/runs/${run.id}/${body.mode==="automated" ? "test" : "trigger"}`,{confirmed:approved});
        el("consent").checked=false;
      }else if(action==="watch"){
        const saved=JSON.parse(localStorage.getItem("shoptalk-session") || "{}"),order=el("order-id").value.trim() || saved.order_id;
        if(!/^[0-9a-f-]{36}$/i.test(order || ""))throw new Error("Place a new order in the store, then enter its order ID.");result=await api(`/runs/${current.run.id}/watch/${order}`,{});
      }else result=await api(`/runs/${current.run.id}/${action}`,{confirmed:el("consent").checked});render(result);
      if(action==="prepare")el("journal").closest(".failure-log-panel").scrollIntoView({behavior:"smooth",block:"center"});
    }catch(e){error(e.message);await refreshController();}finally{busy=false;buttons();}
  }
  async function download(id) {
    try{const response=await fetch(`${endpoint}/evidence/${id}`,{cache:"no-store",credentials:"omit",signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error("Evidence download unavailable");const url=URL.createObjectURL(await response.blob()),a=make("a");a.href=url;a.download=`failure-demo-${id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){error(e.message);}
  }
  el("connect").addEventListener("click",refreshController);for(const id of ["prepare","recover","retry","verify","watch"])el(id).addEventListener("click",()=>act(id));
  el("evidence").addEventListener("click",()=>download(current.run.id));el("scenario").addEventListener("change",selection);el("mode").addEventListener("change",selection);el("consent").addEventListener("change",buttons);
  document.addEventListener("visibilitychange",()=>{clearTimeout(poll);if(!document.hidden)refreshController();});
  window.addEventListener("storage",event=>{if(event.key==="shoptalk-session" && current?.run?.mode==="manual" && document.activeElement!==el("order-id")){try{const id=JSON.parse(event.newValue || "{}").order_id;if(id && !current.run.baseline_orders.includes(id))el("order-id").value=id;}catch{/* wait for input */}}});selection();
  window.addEventListener("observation-refresh",refreshController);
  document.getElementById("failure-demo").addEventListener("toggle",e=>{if(e.target.open)refreshController();});
  refreshController();
})();
