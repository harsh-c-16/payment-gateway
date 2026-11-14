"use strict";
(() => {
  const M=window.JourneyModel,V=window.JourneyView,{$,n,fmt,ms,age,stamp,short,json}=V;
  const base="http://127.0.0.1:8010";
  let data=null,paused=false,busy=false,stale=false,timer=null,trace=null,eventKey=null,stageKey="bronze",traceSequence=0,selectedScenario="duplicate",labRun=null,selectedNamespace="";
  let labShown=null,labWorkerActive=false,testBusy=false,labTimer=null,labPolling=false,refreshQueued=false,pendingTraceFirst=false;
  const autoRuns=new Set(),finishRequests=new Set();
  const localTime=value=>new Date(value).toLocaleString('en-IN',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
  const testCases={
    duplicate:{title:"Send the same event twice",description:"Send three messages, including a repeated event.",expected:"Analytics should count two unique events.",purchases:0},
    malformed:{title:"Send a bad message",description:"Send one broken message between two valid events.",expected:"Reject the bad message and process the two valid events.",purchases:0},
    conflict:{title:"Send a changed duplicate",description:"Reuse an event ID with different contents.",expected:"Keep the original event and reject the changed copy.",purchases:0},
    out_of_order:{title:"Send stock updates in the wrong order",description:"Send a newer stock update before an older one.",expected:"Keep the newer stock value.",purchases:0},
    late_event:{title:"Send an event late",description:"Send an event for an earlier time period.",expected:"Update the earlier analytics result without losing the event.",purchases:0},
    replay:{title:"Rebuild analytics from saved events",description:"Process the saved events again in a separate test dataset.",expected:"The rebuilt result should match the original.",purchases:0},
    race:{title:"Two buyers, one item",description:"Two simulated buyers try to buy the last available item.",expected:"One purchase succeeds, one is rejected, and only one payment is taken.",purchases:2}
  };
  const activeRun=()=>labWorkerActive || ["Running","Awaiting recovery","Interrupted"].includes(labRun?.status);
  const shownRun=()=>labShown?.scenario===selectedScenario ? labShown : null;
  const stages={
    csv:["CSV","Read the original product CSV. Stock and payments are created separately by the demo."],
    archive:["Raw archive","Keep an unchanged copy of the CSV so the import can be checked or repeated."],
    normalize:["Clean rows","Check each row and turn values into a consistent format. Missing values stay unknown."],
    deduplicate:["Remove duplicates","Choose one current product record and keep track of duplicate or conflicting rows."],
    catalogue:["Products","Save the cleaned product records and prices for the store."],
    search:["Search","Find products using the shopper’s filters and the latest stock updates."],
    checkout:["Checkout","The shopper confirms the items and price. Retrying the same request should create one order."],
    services:["Services","Orders, Inventory and Payments handle their own steps and save the results."],
    outbox:["Save events","Save an event with the business change, then send it to Kafka."],
    kafka:["Kafka","Queue events so the other services can read them."],
    bronze:["Bronze","Keep the original event with its Kafka position and a file reference."],
    silver:["Silver","Check events, remove identical duplicates and set aside bad records."],
    gold:["Gold","Build the analytics tables and make the completed version available to query."],
    queries:["Query result","Check that the event is in the current analytics version and read the result."],
    projection:["Catalogue stock projection","Update product availability when a newer stock event arrives. Ignore older versions."]
  };
  const catalogueKeys=["csv","archive","normalize","deduplicate","catalogue","search"],transactionKeys=["checkout","services","outbox","kafka","bronze","silver","gold","queries"];
  async function request(path,options={}) {
    const response=await fetch(base+path,{cache:"no-store",credentials:"omit",...options,
      headers:{"Content-Type":"application/json",...(options.headers || {})},signal:AbortSignal.timeout(40000)});
    if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.detail || `Controller HTTP ${response.status}`);}
    return response.json();
  }
  function error(message){$("journey-error").hidden=false;$("journey-error").textContent=message;}
  function mode() {
    $("journey-mode").textContent=stale ? "Unavailable / stale" : paused ? "Paused" : data ? "Live" : "Unavailable";
    $("journey-mode").className="badge"+((paused || stale || !data) ? " warning" : "");
    $("journey-pause").textContent=paused ? "Resume" : "Pause";$("journey-pause").disabled=false;
    $("journey-refresh").disabled=busy;
    const active=activeRun(),resume=active && ["Awaiting recovery","Interrupted"].includes(labRun?.status);
    $("lab-start").textContent=testBusy ? "Starting…" : resume ? "Resume test" : active ? "Test running…" : shownRun() ? "Run again" : "Run test";
    $("lab-start").disabled=testBusy || !data || (active ? !resume : !!testCases[selectedScenario]?.purchases && !$("lab-consent").checked);
    $("lab-scenario").disabled=testBusy || active;
    $("lab-consent").disabled=testBusy || active;
    $("lab-history-open").disabled=testBusy || active || !$("lab-history").value;
    $("lab-history").disabled=testBusy || active;
    $("source-banner").hidden=!selectedNamespace;
  }
  function stageState(key) {
    if(!data)return {status:"unavailable",label:"Unavailable"};
    const events=data.events || [],chosen=trace?.events?.find(e=>e.key===eventKey),r=chosen?.receipt;
    const catalogue=data.catalogue || {};
    if(catalogueKeys.includes(key)) {
      if(key==="archive")return {status:catalogue.source?.archive_verified===true ? "observed" : catalogue.source?.archive_verified===false ? "failed" : "unavailable",label:catalogue.source?.archive_verified===true ? "Archive hash verified" : catalogue.source?.archive_verified===false ? "Matching archive missing" : "Archive not verified"};
      if(key==="search"){const matches=events.filter(e=>["SEARCH_REQUESTED","PRODUCT_RETRIEVED"].includes(e.event_type));return {status:matches.length ? "observed" : "unavailable",label:matches.length ? `${matches.length} observed events` : "No search observation"};}
      const present=key==="csv" || key==="archive" ? catalogue.source : catalogue.normalization;
      return {status:present ? "observed" : "unavailable",label:present ? "Import recorded" : "No reading"};
    }
    if(chosen && ["bronze","silver","gold","kafka"].includes(key)) {
      const state=M.timeline(chosen,data.clock).find(stage=>stage.key===key)?.status || "unavailable";
      return {status:state,label:state==="observed" ? "Event recorded" : state==="failed" ? "Quarantined" : state==="pending" ? "Pending observation" : "No reading"};
    }
    if(key==="outbox"){const known=data.outboxes?.every(r=>r.pending!==null);return {status:known ? "observed" : "unavailable",label:known ? `${data.outboxes.reduce((s,r)=>s+r.pending,0)} pending` : "Audit unavailable"};}
    if(key==="queries")return {status:trace?.visibility?.queryable ? "observed" : "unavailable",label:trace?.visibility?.queryable ? `Queried generation ${trace.visibility.generation}` : "No query yet"};
    if(key==="gold")return {status:data.manifests?.gold ? "observed" : "unavailable",label:data.manifests?.gold ? `Generation ${data.manifests.gold.generation}` : "No active manifest observed"};
    if(key==="silver")return {status:data.manifests?.silver ? "observed" : "unavailable",label:data.manifests?.silver ? `Generation ${data.manifests.silver.generation}` : "Unavailable"};
    if(key==="projection"){const known=events.filter(e=>e.projection);return {status:known.length ? "observed" : "unavailable",label:`${known.length} linked receipts`};}
    const known=key==="checkout" ? events.filter(e=>e.event_type==="CHECKOUT_STARTED") : events;
    return {status:known.length ? "observed" : "unavailable",label:known.length ? `${known.length} recent events` : "No events yet"};
  }
  function drawPaths() {
    for(const [target,keys]of [["catalogue-path",catalogueKeys],["transaction-path",transactionKeys]]) {
      $(target).replaceChildren();for(const key of keys){const state=stageState(key),button=n("button","",`stage-button ${state.status}`);button.type="button";button.dataset.stage=key;button.setAttribute("aria-pressed",String(stageKey===key));button.classList.toggle("selected",stageKey===key);button.classList.toggle("path-highlight",!!eventKey && transactionKeys.includes(key) && state.status==="observed");button.append(n("strong",stages[key][0]),n("small",state.label));button.addEventListener("click",()=>selectStage(key));$(target).append(button);}
    }
    selectStage(stageKey,false);
  }
  function selectStage(key,redraw=true) {
    stageKey=key;$("stage-name").textContent=stages[key][0];$("stage-purpose").textContent=stages[key][1];
    const state=stageState(key),c=data?.catalogue || {},e=trace?.events?.find(e=>e.key===eventKey),r=e?.receipt || {},g=data?.manifests?.gold;
    let values=[["State",state.label],["Observed at",stamp(data?.observed_at)]];
    if(key==="csv" || key==="archive")values.push(["Source rows",fmt(c.source?.row_count)],["SHA-256",c.source?.source_sha256],["Archived path",c.source?.raw_archive_descriptor?.path],["Acquired at",stamp(c.source?.acquired_at)]);
    else if(["normalize","deduplicate","catalogue"].includes(key))values.push(["Rules version",c.normalization?.rules_version || c.source?.rules_version],["Dataset revision",c.normalization?.dataset_revision],["Canonical rows",fmt(c.normalization?.canonical_rows)],["Active rows",fmt(c.normalization?.active_rows)],["Timing evidence",c.timings ? json(c.timings.stages) : null]);
    else if(key==="outbox")values.push(["Pending by service",data?.outboxes?.map(r=>`${r.service}: ${fmt(r.pending)}`).join(" · ")],["Scope","Entire displayed namespace; each service audit is separate"]);
    else if(key==="gold" || key==="queries")values.push(["Latest active generation",fmt(g?.generation)],["Publication time",stamp(g?.created_at)],["Transform version",g?.transform_version],["Selected event first visibility",fmt(r.visibility_generation)],["Exact membership",trace?.visibility?.queryable ? trace.visibility.visible_event_ids?.includes(e?.event_id) ? "Present in queryable active generation" : "Not present in queried active generation" : "Unavailable"]);
    else if(key==="projection")values.push(["Selected event outcome",e?.projection?.outcome],["Previous → current version",e?.projection ? `${e.projection.previous_version} → ${e.projection.current_version}` : null],["Commit observation",stamp(e?.projection?.observed_commit_at)],["Bound","Latest linked events; projection API sample capped at 1,000"]);
    else values.push(["Selected event",e?.event_id],["Kafka coordinate",e?.source ? `${e.source.topic} / ${e.source.partition}:${e.source.offset}` : null],["Bronze locator",r.source?.raw_locator],["Disposition",r.disposition],["Reason",r.reason_code || "None recorded"]);
    V.fields("stage-observation",values);
    if(redraw)document.querySelectorAll("[data-stage]").forEach(button=>{button.classList.toggle("selected",button.dataset.stage===key);button.setAttribute("aria-pressed",String(button.dataset.stage===key));});
  }
  function recentActions() {
    const select=$("recent-actions"),old=select.value;select.replaceChildren(n("option","Select an order, search or event"));select.firstChild.value="";
    const choices=new Map();for(const e of data?.events || []) {
      const order=e.payload?.order_id,search=e.payload?.search_id;
      const kind=order ? "order" : search ? "search" : "event",id=order || search || e.event_id;
      if(id && !choices.has(`${kind}:${id}`))choices.set(`${kind}:${id}`,`${kind.toUpperCase()} · ${short(id)} · ${e.event_type || "Unidentified delivery"}`);
    }
    for(const [value,label]of [...choices].sort(([a],[b])=>Number(a.startsWith("event:"))-Number(b.startsWith("event:"))).slice(0,25)){const option=n("option",label);option.value=value;select.append(option);}select.value=old;
  }
  function traceGraph() {
    const events=trace?.events || [];$("trace-graph").replaceChildren();
    document.querySelector(".trace-layout").hidden=!events.length;
    $("timeline-panel").hidden=!events.length;
    $("trace-count").textContent=trace ? `${new Set(events.map(e=>e.event_id).filter(Boolean)).size} unique events · ${events.length} messages` : "Choose an action above.";
    if(!events.length){$("trace-graph").append(n("p",trace ? "No matching observations. Check the identity, namespace, provider availability and sample bounds." : "Choose an order or search to see its events.","empty"));return;}
    $("trace-graph").append(n("div",`${trace.kind.toUpperCase()} · ${trace.id}`,"trace-root"));
    const services=new Map();for(const e of events){const service=e.source_service || "Unavailable producer";if(!services.has(service))services.set(service,[]);services.get(service).push(e);}
    for(const [service,branch]of services){const lane=n("div","","service-lane");lane.append(n("h4",`${service} · ${branch.length} ${branch.length===1 ? "delivery" : "deliveries"}`));
      for(const e of [...branch].sort((a,b)=>(a.aggregate_version || 0)-(b.aggregate_version || 0))){const row=n("div","","event-branch"),button=n("button","",`event-button${e.key===eventKey ? " selected" : ""}`);button.type="button";button.dataset.eventKey=e.key;button.setAttribute("aria-pressed",String(e.key===eventKey));button.append(n("strong",e.event_type || "Event type unavailable"),n("small",`${short(e.event_id)} · v${e.aggregate_version ?? "?"}`));button.addEventListener("click",()=>inspect(e.key));const r=e.receipt,state=r?.disposition==="invalid" ? "failed" : r?.gold_visible_at ? "observed" : "pending",trail=n("div",r ? `Kafka ${r.source.partition}:${r.source.offset} → Bronze → ${r.disposition==="invalid" ? "Quarantine" : r.disposition==="duplicate_delivery" ? "Duplicate suppressed" : "Silver"} ${r.gold_visible_at ? "→ active Gold" : "· Gold not observed"}` : e.outbox_pending ? "Outbox pending → Kafka not observed" : "Kafka / sink receipt unavailable",`event-trail ${state}`);row.append(button,trail);if(e.source_service==="inventory")row.append(n("div",`↳ Catalogue stock projection · ${e.projection ? `${e.projection.outcome} · v${e.projection.previous_version} → v${e.projection.current_version}` : "receipt unavailable in bounded sample"}`,"event-projection"));lane.append(row);}
      $("trace-graph").append(lane);
    }
  }
  function inspect(key) {
    eventKey=key;const e=trace?.events.find(e=>e.key===key);if(!e)return;const r=e.receipt || {},source=e.source || r.source;
    $("inspector-title").textContent=e.event_type || "Unidentified event";$("copy-event-id").disabled=!e.event_id;
    V.fields("record-fields",[["Event ID",e.event_id],["Event type",e.event_type],["Producing service",e.source_service],["Correlation ID",e.correlation_id],
      ["Business ID",e.payload?.order_id || e.payload?.search_id || e.aggregate_id],["Kafka topic",source?.topic],["Partition / offset",source ? `${source.partition} / ${source.offset}` : null],
      ["Bronze source",r.source?.raw_locator],["Content SHA-256",r.raw_sha256],["Silver disposition",{new_valid:"Accepted",duplicate_delivery:"Duplicate",invalid:"Quarantined",redelivery_noop:"Source redelivery · no-op"}[r.disposition] || "Unavailable"],
      ["Quarantine reason",r.reason_code || "None recorded"],["Gold first generation",fmt(r.visibility_generation)],["Gold visibility observed",stamp(r.gold_visible_at)],["Latest queried generation",fmt(trace.visibility?.generation)],
      ["Exact active membership",trace.visibility?.queryable ? trace.visibility.visible_event_ids?.includes(e.event_id) ? "Present" : "Absent in the pinned active generation" : "Unavailable"],["Timing validity",r.timing_validity || "missing"]]);
    V.fields("record-summary",[["Event",e.event_type],["Service",e.source_service],["Processing",r.disposition==="invalid" ? "Rejected" : r.gold_visible_at ? "In analytics" : r.disposition==="duplicate_delivery" ? "Duplicate ignored" : "Waiting"],["Analytics version",r.visibility_generation]]);
    V.fields("business-result",[["Table",trace.business_result?.table],["Version",trace.business_result?.generation],...Object.entries(trace.business_result?.rows?.[0] || {}).filter(([key])=>key!=="namespace")]);
    V.fields("transformation-result",[["Schema version",e.schema_version],["Data version",data?.manifests?.gold?.transform_version],["Event time",stamp(e.event_time)],["Saved time",stamp(e.produced_at)],["Stock update",e.projection?.outcome]]);
    const timeline=trace.timelines?.[key] || M.timeline(e,data?.clock);$("action-timeline").replaceChildren();
    for(const stage of timeline){const li=n("li","",stage.status);li.append(n("strong",stage.label),n("time",stage.at ? stamp(stage.at) : stage.status==="failed" ? "Quarantined · excluded from Gold" : stage.status==="pending" ? "Pending observation" : "Unavailable"),n("small",stage.ordering ? "Invalid clock order · duration unavailable" : stage.since_previous_observed_ms!==null ? `+ ${ms(stage.since_previous_observed_ms)} since previous observed stage` : "No duration observation"));if(stage.timing_validity!=="observed")li.append(n("small",`Timing: ${stage.timing_validity}`));$("action-timeline").append(li);}
    const total=M.elapsed(e.produced_at,r.gold_visible_at),qualified=data?.clock?.status==="qualified" && r.timing_validity==="observed";
    $("overall-latency").textContent=qualified && total!==null ? `Time to analytics: ${ms(total)}` : "Time not measured";
    $("timeline-clock").textContent=`Clock: ${data?.clock?.status || "unavailable"} · error bound ${ms(data?.clock?.error_bound_ms)}. Post-commit timestamps are observation upper bounds. Missing stages remain missing; inter-stage durations can span an unavailable stage.`;
    const summary=M.latency(trace.events,data?.clock);$("action-completion").replaceChildren();for(const [label,value]of [["Events",summary.cohort_count],["In analytics",summary.completed_count],["Waiting",summary.unresolved_count]]){const d=n("div",label);d.append(n("strong",fmt(value)));$("action-completion").append(d);}
    traceGraph();drawPaths();
  }
  async function loadTrace(kind,id) {
    const sequence=++traceSequence;
    $("trace-kind").value=kind;$("trace-id").value=id;$("trace-submit").disabled=true;
    try {
      const next=await request(`/journey/trace?kind=${encodeURIComponent(kind)}&id=${encodeURIComponent(id)}${selectedNamespace ? "&namespace="+encodeURIComponent(selectedNamespace) : ""}`);
      if(sequence!==traceSequence)return;
      trace=next;$("trace-note").textContent=`Live view · ${next.events.length} event records`;
      eventKey=trace.events.some(e=>e.key===eventKey) ? eventKey : trace.events[0]?.key;
      traceGraph();if(eventKey)inspect(eventKey);
    } catch(e){error(`Trace unavailable: ${e.message}`);}finally{$("trace-submit").disabled=false;}
  }
  function scenarioCards() {
    const select=$("lab-scenario");
    if(!select.options.length)for(const [id,info] of Object.entries(testCases))select.append(new Option(info.title,id));
    select.value=selectedScenario;
  }
  function selectScenario(id) {
    selectedScenario=id;labShown=null;$("lab-consent").checked=false;renderTest();
  }
  const processingRules={
    duplicate:"Deduplication: repeated delivery of the same event ID and content must produce one Silver row and one Gold contribution.",
    conflict:"Conflict detection: an existing event ID with changed content must be quarantined with EVENT_ID_CONFLICT; the original remains valid.",
    malformed:"Fault isolation: invalid JSON must be quarantined with INVALID_JSON while valid messages continue to Silver and Gold.",
    out_of_order:"Version ordering: the catalogue stock projection applies a newer stock_version and rejects stale versions. Both valid events remain in the analytical history.",
    late_event:"Event-time reconciliation: a late event revises its earlier time window in a new Gold publication instead of being dropped or counted in the current window.",
    replay:"Replay consistency: rebuild analytics from archived events in an isolated output and reconcile against the original; repeated replay must not multiply logical effects.",
    race:"Concurrency control: two independent checkout requests compete for one unit. Reconcile terminal orders, stock, payment ledger and active Gold; only one sale and one matching debit are allowed."
  };
  function checkValue(name,value) {
    if(value===null || value===undefined)return "Not observed";
    if(Array.isArray(value)){
      if(name==="Newer projection preserved")return `stock_version=${value[0]}, available=${value[1]}`;
      if(name==="No overselling; last unit consumed")return `on_hand=${value[0]}, reserved=${value[1]}, available=${value[2]}`;
      return value.map(v=>checkValue("",v)).join("; ") || "No rows";
    }
    if(typeof value==="object")return Object.entries(value).map(([k,v])=>`${k}=${checkValue("",v)}`).join(", ");
    return String(value);
  }
  function renderEvidence(run) {
    const labels=new Map(),seen=new Map();
    const rows=(run.emissions || []).map((delivery,i)=>{
      const id=delivery.event_id,count=seen.get(id) || 0;seen.set(id,count+1);
      if(id && !labels.has(id))labels.set(id,`E${labels.size+1}`);
      const event=(run.events || []).filter(e=>e.event_id===id)[count];
      const receipt=delivery.source && (run.receipts || []).find(r=>r.source?.topic===delivery.source?.topic && r.source?.partition===delivery.source?.partition && r.source?.offset===delivery.source?.offset);
      const payload=event?.payload || {};
      const fields=[event?.event_type || (delivery.kind==="malformed_fixture" ? "Invalid JSON" : "No decoded event"),...Object.entries(payload).filter(([k])=>["stock_version","available","on_hand","reserved","duration_ms","mode","outcome"].includes(k)).map(([k,v])=>`${k}=${v}`)];
      if(event?.event_time)fields.push(`event_time=${event.event_time}`);
      return [`${i+1} / ${labels.get(id) || "No event ID"}`,fields.join(" | "),delivery.source ? `${delivery.source.partition}:${delivery.source.offset}` : "Not acknowledged",receipt ? [receipt.disposition,receipt.reason_code].filter(Boolean).join(" | ") : "Not observed"];
    });
    if(run.scenario==="race")for(const [i,request] of (run.requests || []).entries()){
      const order=run.orders?.find(o=>o.order_id===request.order_id);
      rows.push([`Checkout ${i+1}`,`${request.user_id} | quantity=${order?.lines?.reduce((s,l)=>s+l.quantity,0) ?? "Not observed"}`,"See order event trace",order?.status || "Not observed"]);
    }
    V.rows("lab-inputs",rows,"No sent input observed yet.");
    const target=$("lab-checks");
    for(const c of run.checks || []){
      const row=n("tr");
      for(const value of [c.name,checkValue(c.name,c.expected),checkValue(c.name,c.observed)])row.append(n("td",value));
      const cell=n("td");cell.append(n("strong",c.passed===true ? "PASS" : c.passed===false ? "FAIL" : "Not measured",`verdict ${c.passed===false ? "failed" : ""}`));row.append(cell);target.append(row);
    }
    if(!run.checks?.length)V.rows("lab-checks",[],"Verification has not completed. No pass is inferred.");
  }
  function renderTest() {
    const info=testCases[selectedScenario],run=shownRun();
    $("lab-rule").textContent=processingRules[selectedScenario];
    $("lab-explanation").textContent=info.description;$("lab-verification").textContent="Expected: "+info.expected;
    $("lab-consent-label").hidden=!info.purchases;
    $("lab-result").hidden=!run;$("lab-progress").hidden=!run;
    $("lab-export").disabled=!run;$("lab-show-data").hidden=!run?.receipts?.length && !run?.business_result;
    $("lab-checks").replaceChildren();
    if(!run){$("lab-status").textContent="Ready";$("lab-message").textContent=activeRun() ? `A previous test is still running: ${testCases[labRun.scenario]?.title || "test"}.` : "Click Run test. It sends the data, processes it and checks the result.";mode();return;}
    const incomplete=!!run.error_type || ["Unavailable","Interrupted"].includes(run.status) || run.status==="Failed" && !run.checks?.some(c=>c.passed===false);
    $("lab-status").textContent=incomplete ? "Could not finish" : run.status==="Awaiting recovery" ? "Processing" : run.status;
    $("lab-status").className="badge"+(incomplete || run.status==="Failed" ? " warning" : "");
    $("lab-message").textContent=incomplete ? "The test stopped before verification completed. Try again or download the report." : run.status==="Passed" ? "The result matches what we expected." : run.status==="Failed" ? "The result did not match. See the checks below." : "Running the test. This usually takes a few seconds.";
    $("lab-result-title").textContent=testCases[run.scenario].title;
    $("lab-result-time").textContent="Run on "+localTime(run.started_at);
    renderEvidence(run);
    const sent=!!run.emissions?.length || !!run.requests?.length,processed=!!run.receipts?.length || !!run.orders?.length,checked=!!run.business_result;
    [...$("lab-progress").children].forEach((li,i)=>{li.className=[sent,processed,checked][i] ? "done" : incomplete ? "stopped" : "";});mode();
  }
  function renderLab(value) {
    labRun=value?.run || null;labWorkerActive=value?.worker_active===true;scenarioCards();
    if(labShown?.id===labRun?.id)labShown=labRun;
    const history=$("lab-history"),fingerprint=(value?.history || []).map(r=>r.id+":"+r.status).join(",");
    if(history.dataset.history!==fingerprint){const previous=history.value;history.replaceChildren(new Option("Choose an earlier test",""));for(const run of value?.history || [])history.append(new Option(`${testCases[run.scenario]?.title || "Test"} · ${localTime(run.started_at)} · ${run.status}`,run.id));history.value=previous;history.dataset.history=fingerprint;}
    renderTest();
    if(labRun?.status==="Awaiting recovery" && autoRuns.has(labRun.id))finishTest(labRun.id);
  }
  async function finishTest(id) {
    if(finishRequests.has(id))return;finishRequests.add(id);
    try {renderLab(await request(`/journey/lab/${id}/recover`,{method:"POST"}));}
    catch(e){autoRuns.delete(id);finishRequests.delete(id);error("The test paused. Click Resume test to continue.");}
  }
  async function watchLab() {
    clearTimeout(labTimer);if(labPolling)return;labPolling=true;
    try {const value=await request("/journey/lab");renderLab(value);}
    catch(e){error("Test updates are unavailable. Click Refresh to reconnect.");}
    finally{labPolling=false;if(activeRun())labTimer=setTimeout(watchLab,1000);}
  }
  function setScope(namespace) {
    selectedNamespace=namespace;traceSequence++;trace=null;eventKey=null;$("trace-note").textContent="";traceGraph();
    $("source-banner").hidden=!namespace;$("journey-scope").textContent=namespace ? `Showing test data: ${testCases[shownRun()?.scenario]?.title || "saved test"}` : "Store activity";
    if(busy)refreshQueued=true;else refresh(true);
  }
  function render(next) {
    data=next;
    $("journey-updated").textContent=`Updated ${localTime(next.observed_at)}`;
    $("journey-export").disabled=false;
    drawPaths();recentActions();renderLab(next.lab);mode();
    if(pendingTraceFirst){pendingTraceFirst=false;const first=next.events.find(e=>e.event_id);if(first)loadTrace("event",first.event_id);}
  }
  async function refresh(manual=false) {
    clearTimeout(timer);if(busy || (paused && !manual))return;busy=true;mode();
    const requestedNamespace=selectedNamespace;
    try {const next=await request("/journey/snapshot"+(selectedNamespace ? "?namespace="+encodeURIComponent(selectedNamespace) : ""));if(requestedNamespace!==selectedNamespace)return;stale=false;$("journey-updated").classList.remove("stale-label");render(next);$("journey-error").hidden=true;
      if(next.unavailable?.length)error("Some data could not be read. Try Refresh.");
      if(trace)await loadTrace(trace.kind,trace.id);
    }catch(e){stale=true;error(`${data ? "Displayed observations are stale; their original timestamps are retained. " : "No live observations yet. "}${e.message}. Start .\\start-failure-demo.ps1 after the prototype.`);$("journey-updated").classList.add("stale-label");}
    finally{busy=false;mode();if(refreshQueued){refreshQueued=false;timer=setTimeout(()=>refresh(true),0);}else if(!paused && !document.hidden)timer=setTimeout(refresh,5000);}
  }
  function download(value,name){const url=URL.createObjectURL(new Blob([json(value)],{type:"application/json"})),a=n("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $("trace-form").addEventListener("submit",e=>{e.preventDefault();loadTrace($("trace-kind").value,$("trace-id").value.trim());});
  $("recent-actions").addEventListener("change",()=>{const [kind,id]=$("recent-actions").value.split(":");if(id)loadTrace(kind,id);});
  $("projection-stage").addEventListener("click",()=>selectStage("projection"));
  $("copy-event-id").addEventListener("click",()=>{const id=trace?.events.find(e=>e.key===eventKey)?.event_id;if(id)navigator.clipboard?.writeText(id).catch(()=>error("Clipboard unavailable. The event ID is visible in the inspector."));});
  $("journey-pause").addEventListener("click",()=>{paused=!paused;clearTimeout(timer);mode();if(!paused)refresh();});
  $("journey-refresh").addEventListener("click",()=>refresh(true));
  $("journey-export").addEventListener("click",()=>{if(data)download({...data,selected_trace:trace},`data-journey-${data.namespace}-${Date.now()}.json`);});
  $("lab-scenario").addEventListener("change",()=>selectScenario($("lab-scenario").value));
  $("lab-consent").addEventListener("change",mode);
  $("lab-start").addEventListener("click",async()=>{
    if(testBusy)return;
    if(activeRun()){
      if(!["Awaiting recovery","Interrupted"].includes(labRun.status))return;
      selectedScenario=labRun.scenario;labShown=labRun;autoRuns.add(labRun.id);finishRequests.delete(labRun.id);scenarioCards();await finishTest(labRun.id);watchLab();return;
    }
    if(testCases[selectedScenario].purchases && !$("lab-consent").checked)return;
    testBusy=true;labShown=null;renderTest();
    try {const state=await request("/journey/lab/start",{method:"POST",body:JSON.stringify({scenario:selectedScenario,confirmed:true})});labShown=state.run;autoRuns.add(state.run.id);$("lab-consent").checked=false;renderLab(state);watchLab();}
    catch(e){$("lab-message").textContent=e.message;$("lab-status").textContent="Could not start";}
    finally{testBusy=false;mode();}
  });
  $("lab-export").addEventListener("click",()=>{const run=shownRun();if(run)download(run,`test-result-${run.id}.json`);});
  $("lab-show-data").addEventListener("click",()=>{const run=shownRun();if(!run)return;pendingTraceFirst=true;setScope(run.namespace);$("trace").scrollIntoView({behavior:"smooth"});});
  $("lab-history").addEventListener("change",mode);
  $("lab-history-open").addEventListener("click",async()=>{const id=$("lab-history").value;if(!id)return;try{labShown=await request(`/journey/lab/${id}`);selectedScenario=labShown.scenario;$("lab-consent").checked=false;scenarioCards();renderTest();}catch(e){error("That test result could not be opened.");}});
  $("store-data").addEventListener("click",()=>{pendingTraceFirst=false;setScope("");});
  document.addEventListener("visibilitychange",()=>{clearTimeout(timer);if(!document.hidden && !paused)refresh();});
  scenarioCards();drawPaths();renderTest();mode();refresh();
})();
