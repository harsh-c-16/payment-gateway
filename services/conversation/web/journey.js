"use strict";
(() => {
  const M=window.JourneyModel,V=window.JourneyView,{$,n,fmt,ms,age,stamp,short,json}=V;
  const base="http://127.0.0.1:8010";
  let data=null,paused=false,busy=false,stale=false,timer=null,trace=null,eventKey=null,stageKey="bronze",recording=null,frame=0,playing=false,playTimer=null,traceSequence=0,selectedScenario=null,labRun=null,recordingId=null,selectedNamespace="";
  const stages={
    csv:["CSV","Verify source checksum, CSV structure and immutable observation identities. The original historical source has no live stock or payment data."],
    archive:["Raw archive","Retain the original CSV by content hash before normalization. The archive is separate from event-stream Bronze."],
    normalize:["Validate / normalize","Parse bounded source fields, normalize values deterministically, preserve provenance and retain missing attributes as null."],
    deduplicate:["Deduplicate","Select the latest observation per source PID. Keep superseded source rows and withhold conflicting latest identities."],
    catalogue:["Catalogue","Promote canonical listings with authoritative integer prices and dataset revisions. Simulation stock is maintained separately."],
    search:["Search","Apply recorded filters and the catalogue stock projection. Availability is a display hint and is revalidated at checkout."],
    checkout:["Checkout","An explicit confirmation binds the quote and cart version. Idempotency preserves the identity of a repeated request."],
    services:["Orders / Inventory / Payments","A durable saga coordinates independent service transactions. One order can produce multiple events on several branches."],
    outbox:["Transactional outboxes","Store immutable events in the same transaction as each service's business change. Relays publish them at least once."],
    kafka:["Kafka","Retain ordered records within each topic partition. Consumer-group committed offsets measure one backlog boundary."],
    bronze:["Bronze","Durably capture original Kafka bytes with their topic, partition, offset, raw hash and file/row locator before acknowledging durable processing."],
    silver:["Silver","Validate and normalize each delivery. Accept a new event ID, suppress an identical duplicate, or quarantine conflicting and malformed input."],
    gold:["Active Gold","Publish versioned immutable Parquet files and atomically activate their manifest. Durable Silver alone does not establish query visibility."],
    queries:["Analytical queries","Pin one active manifest generation at query start. Exact event membership and the corresponding business result are separate checks."],
    projection:["Catalogue stock projection","Inventory events update absolute stock only when their versions are newer. Late older versions must not replace newer state."]
  };
  const catalogueKeys=["csv","archive","normalize","deduplicate","catalogue","search"],transactionKeys=["checkout","services","outbox","kafka","bronze","silver","gold","queries"];
  const fallbackScenarios={
    race:{title:"Two shoppers, one unit",purchase_count:2,explanation:"Two confirmed checkouts compete for one isolated unit.",preconditions:"Real transactional services, Kafka, relays and scoped success plans ready.",recovery:"Finish observation and publish isolated analytics.",verification:"One confirmed sale; stock never negative; one matching debit; final Gold reconciles."},
    duplicate:{title:"Identical duplicate delivery",purchase_count:0,explanation:"Deliver one immutable event twice at different Kafka offsets.",preconditions:"Kafka and analytical storage ready.",recovery:"Drain and publish valid facts.",verification:"Multiple deliveries; one analytical contribution per unique ID."},
    conflict:{title:"Same ID, conflicting payload",purchase_count:0,explanation:"Change the second payload while preserving its event ID.",preconditions:"Kafka, schema cache and analytics ready.",recovery:"Publish valid facts and retain quarantine.",verification:"EVENT_ID_CONFLICT reason and original result preserved."},
    out_of_order:{title:"Out-of-order stock updates",purchase_count:0,explanation:"Stock version 2 arrives before version 1.",preconditions:"Isolated catalogue and stock consumer ready.",recovery:"Drain projection and publish analytics.",verification:"Version 2 applied; version 1 stale; newer state preserved."},
    late_event:{title:"Late analytical event",purchase_count:0,explanation:"An old event-time window receives another fact after the watermark advances.",preconditions:"Kafka and retained lakehouse storage ready.",recovery:"Publish the late correction.",verification:"LATE_RECONCILIATION and a newer Gold revision."},
    malformed:{title:"Malformed event among valid events",purchase_count:0,explanation:"Place malformed JSON between two valid events.",preconditions:"Kafka and analytical storage ready.",recovery:"Publish valid facts and retain quarantine.",verification:"INVALID_JSON quarantined; valid traffic continues."},
    replay:{title:"Isolated analytical replay",purchase_count:0,explanation:"Rebuild a pinned publication in a fresh replay namespace.",preconditions:"An original fixture publication and Bronze archive.",recovery:"Explicit isolated replay and comparison.",verification:"Original/replayed values agree; no operational commands or republishing."}
  };
  const existing=[
    ["analytics","Consumer pause & recovery","Pause the real analytics worker; observe partition lag, then drain and reconcile."],
    ["crash","Crash & restart","Acknowledge the saga.after_commit crash boundary, then recover without repeated business effects."],
    ["late","Reservation expiry","Observe cancellation, released stock and suppression of an expired pending debit."],
    ["refund","Debit followed by reversal","Observe a real simulated debit, one matching reversal, restored stock and cancelled order."]
  ];
  async function request(path,options={}) {
    const response=await fetch(base+path,{cache:"no-store",credentials:"omit",...options,
      headers:{"Content-Type":"application/json",...(options.headers || {})},signal:AbortSignal.timeout(40000)});
    if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.detail || `Controller HTTP ${response.status}`);}
    return response.json();
  }
  function error(message){$("journey-error").hidden=false;$("journey-error").textContent=message;}
  function mode() {
    $("journey-mode").textContent=recording ? "Saved playback" : stale ? "Unavailable / stale" : paused ? "Paused" : data ? "Live observations" : "Unavailable";
    $("journey-mode").className="badge"+(!recording && (paused || stale || !data) ? " warning" : "");
    $("journey-pause").textContent=paused ? "Resume" : "Pause";$("journey-pause").disabled=!!recording;
    $("journey-refresh").disabled=!!recording || busy;$("journey-record").disabled=!!recording;
    $("lab-start").disabled=!!recording || !selectedScenario || !$("lab-consent").checked || ["Running","Awaiting recovery","Interrupted"].includes(labRun?.status);
    $("lab-recover").disabled=!!recording || !labRun || !["Running","Awaiting recovery","Interrupted"].includes(labRun.status);
    document.body.classList.toggle("playback",!!recording);
    $("namespace-select").disabled=!!recording;
  }
  function stageState(key) {
    if(!data)return {status:"unavailable",label:"Unavailable"};
    const events=data.events || [],chosen=trace?.events?.find(e=>e.key===eventKey),r=chosen?.receipt;
    const catalogue=data.catalogue || {};
    if(catalogueKeys.includes(key)) {
      if(key==="archive")return {status:catalogue.source?.archive_verified===true ? "observed" : catalogue.source?.archive_verified===false ? "failed" : "unavailable",label:catalogue.source?.archive_verified===true ? "Archive hash verified" : catalogue.source?.archive_verified===false ? "Matching archive missing" : "Archive not verified"};
      if(key==="search"){const matches=events.filter(e=>["SEARCH_REQUESTED","PRODUCT_RETRIEVED"].includes(e.event_type));return {status:matches.length ? "observed" : "unavailable",label:matches.length ? `${matches.length} observed events` : "No search observation"};}
      const present=key==="csv" || key==="archive" ? catalogue.source : catalogue.normalization;
      return {status:present ? "observed" : "unavailable",label:present ? "Recorded import evidence" : "Evidence unavailable"};
    }
    if(chosen && ["bronze","silver","gold","kafka"].includes(key)) {
      const state=M.timeline(chosen,data.clock).find(stage=>stage.key===key)?.status || "unavailable";
      return {status:state,label:state==="observed" ? "Observed on selected event" : state==="failed" ? "Quarantined" : state==="pending" ? "Pending observation" : "Evidence unavailable"};
    }
    if(key==="outbox"){const known=data.outboxes?.every(r=>r.pending!==null);return {status:known ? "observed" : "unavailable",label:known ? `${data.outboxes.reduce((s,r)=>s+r.pending,0)} pending` : "Audit unavailable"};}
    if(key==="queries")return {status:trace?.visibility?.queryable ? "observed" : "unavailable",label:trace?.visibility?.queryable ? `Queried generation ${trace.visibility.generation}` : "No query observation"};
    if(key==="gold")return {status:data.manifests?.gold ? "observed" : "unavailable",label:data.manifests?.gold ? `Generation ${data.manifests.gold.generation}` : "No active manifest observed"};
    if(key==="silver")return {status:data.manifests?.silver ? "observed" : "unavailable",label:data.manifests?.silver ? `Generation ${data.manifests.silver.generation}` : "Unavailable"};
    if(key==="projection"){const known=events.filter(e=>e.projection);return {status:known.length ? "observed" : "unavailable",label:`${known.length} linked receipts`};}
    const known=key==="checkout" ? events.filter(e=>e.event_type==="CHECKOUT_STARTED") : events;
    return {status:known.length ? "observed" : "unavailable",label:known.length ? `${known.length} bounded observations` : "No observations"};
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
    for(const [value,label]of [...choices].slice(0,100)){const option=n("option",label);option.value=value;select.append(option);}select.value=old;
  }
  function traceGraph() {
    const events=trace?.events || [];$("trace-graph").replaceChildren();
    $("trace-count").textContent=trace ? `${new Set(events.map(e=>e.event_id).filter(Boolean)).size} logical event IDs · ${events.length} observed deliveries` : "Choose a recent action or enter its UUID";
    if(!events.length){$("trace-graph").append(n("p",trace ? "No matching observations. Check the identity, namespace, provider availability and sample bounds." : "Select an action to reveal its service branches.","empty"));return;}
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
    $("business-result").textContent=json(trace.business_result);
    $("transformation-result").textContent=json({schema_version:e.schema_version,aggregate_type:e.aggregate_type,aggregate_version:e.aggregate_version,
      transform_version:data?.manifests?.gold?.transform_version,publication_code_commit:data?.manifests?.gold?.code_commit,
      metadata:e.metadata || null,event_time:e.event_time,produced_at:e.produced_at,projection:e.projection || null});
    const timeline=trace.timelines?.[key] || M.timeline(e,data?.clock);$("action-timeline").replaceChildren();
    for(const stage of timeline){const li=n("li","",stage.status);li.append(n("strong",stage.label),n("time",stage.at ? stamp(stage.at) : stage.status==="failed" ? "Quarantined · excluded from Gold" : stage.status==="pending" ? "Pending observation" : "Unavailable"),n("small",stage.ordering ? "Invalid clock order · duration unavailable" : stage.since_previous_observed_ms!==null ? `+ ${ms(stage.since_previous_observed_ms)} since previous observed stage` : "No duration observation"));if(stage.timing_validity!=="observed")li.append(n("small",`Timing: ${stage.timing_validity}`));$("action-timeline").append(li);}
    const total=M.elapsed(e.produced_at,r.gold_visible_at),qualified=data?.clock?.status==="qualified" && r.timing_validity==="observed";
    $("overall-latency").textContent=qualified && total!==null ? `Producer → Gold ${ms(total)}` : "Overall qualified latency unavailable";
    $("timeline-clock").textContent=`Clock: ${data?.clock?.status || "unavailable"} · error bound ${ms(data?.clock?.error_bound_ms)}. Post-commit timestamps are observation upper bounds. Missing stages remain missing; inter-stage durations can span an unavailable stage.`;
    const summary=M.latency(trace.events,data?.clock);$("action-completion").replaceChildren();for(const [label,value]of [["Action event IDs",summary.cohort_count],["Gold completed",summary.completed_count],["Unresolved",summary.unresolved_count]]){const d=n("div",label);d.append(n("strong",fmt(value)));$("action-completion").append(d);}
    traceGraph();drawPaths();
  }
  async function loadTrace(kind,id) {
    const sequence=++traceSequence;
    $("trace-kind").value=kind;$("trace-id").value=id;$("trace-submit").disabled=true;
    try {
      let next;
      if(recording)next={kind,id,events:M.related(data?.events || [],kind,id),observed_at:data?.observed_at,
        visibility:data?.selected_trace?.id===id ? data.selected_trace.visibility : null,
        business_result:data?.selected_trace?.id===id ? data.selected_trace.business_result : null};
      else next=await request(`/journey/trace?kind=${encodeURIComponent(kind)}&id=${encodeURIComponent(id)}${selectedNamespace ? "&namespace="+encodeURIComponent(selectedNamespace) : ""}`);
      if(sequence!==traceSequence)return;
      trace=next;$("trace-note").textContent=`${recording ? "Saved observations" : "Targeted audit"} · ${stamp(next.observed_at)} · ${next.events.length} deliveries. Shared correlation IDs alone never establish causality. ${next.unavailable?.length ? "Unavailable: "+next.unavailable.join(", ") : ""}`;
      eventKey=trace.events.some(e=>e.key===eventKey) ? eventKey : trace.events[0]?.key;
      traceGraph();if(eventKey)inspect(eventKey);
    } catch(e){error(`Trace unavailable: ${e.message}`);}finally{$("trace-submit").disabled=false;}
  }
  function scenarioCards(definitions=fallbackScenarios) {
    $("scenario-cards").replaceChildren();
    for(const [id,scenario]of Object.entries(definitions)){const card=n("button","",`scenario-card${id===selectedScenario ? " selected" : ""}`);card.type="button";card.dataset.scenario=id;card.append(n("span","Isolated controlled fixture"),n("strong",scenario.title),n("small",scenario.explanation));card.addEventListener("click",()=>selectScenario(id,definitions));$("scenario-cards").append(card);}
    for(const [id,title,description]of existing){const card=n("a","","scenario-card existing");card.href=`/dashboard?scenario=${id}#failure-demo`;card.append(n("span","Existing real fault mechanism ↗"),n("strong",title),n("small",description));$("scenario-cards").append(card);}
  }
  function selectScenario(id,definitions=fallbackScenarios) {
    selectedScenario=id;const s=definitions[id];$("lab-title").textContent=s.title;$("lab-explanation").textContent=s.explanation;$("lab-preconditions").textContent=s.preconditions;$("lab-recovery-description").textContent=s.recovery;$("lab-verification").textContent=s.verification;$("lab-consent").checked=false;$("lab-consent-text").textContent=s.purchase_count ? `I explicitly authorize ${s.purchase_count} competing simulated purchases using one isolated fixture unit.` : "I authorize publishing this controlled fixture to isolated Kafka topics and analytical state.";
    document.querySelectorAll("[data-scenario]").forEach(e=>e.classList.toggle("selected",e.dataset.scenario===id));mode();
  }
  function renderLab(value) {
    labRun=value?.run || null;if(value?.scenarios)scenarioCards(value.scenarios);
    for(const saved of value?.history || [])if(![...$("namespace-select").options].some(o=>o.value===saved.namespace)){
      const option=n("option",`${saved.scenario} · ${saved.namespace}`);option.value=saved.namespace;$("namespace-select").append(option);
    }
    $("lab-status").textContent=labRun?.status || "NOT_RUN";$("lab-message").textContent=labRun ? `${labRun.message} · ${labRun.namespace}` : "No experiment has started.";$("lab-checks").replaceChildren();
    if(!labRun?.checks?.length)$("lab-checks").append(n("p","Verification has not run. HTTP acceptance alone is not a pass.","empty"));
    for(const c of labRun?.checks || []){const row=n("div"),label=n("span",c.passed===true ? "PASS" : c.passed===false ? "FAIL" : "MISSING",`verdict ${c.passed===false ? "failed" : c.passed===null ? "missing" : ""}`),detail=n("div",c.name);detail.append(n("small",`Expected ${json(c.expected)} · Observed ${json(c.observed)}`));row.append(label,detail);$("lab-checks").append(row);}
    $("lab-journal").replaceChildren();for(const e of (labRun?.journal || []).slice(-20))$("lab-journal").append(n("li",`${stamp(e.at)} · ${e.message}`));
    $("lab-raw").textContent=json(labRun ? {dispositions:labRun.dispositions,receipts:labRun.receipts,projection_receipts:labRun.projection_receipts,
      before_business_result:labRun.before_business_result,business_result:labRun.business_result,replay:labRun.replay,orders:labRun.orders,ledger:labRun.ledger} : null);
    $("lab-export").disabled=!labRun;mode();
  }
  function render(next) {
    data=next;$("journey-scope").textContent=`Namespace: ${next.namespace} · ${next.events.length} bounded event/delivery observations`;
    $("journey-updated").textContent=`Observed ${stamp(next.observed_at)}`;$("journey-clock").textContent=`Clock: ${next.clock?.status || "unavailable"} · bound ${ms(next.clock?.error_bound_ms)}`;
    $("journey-clock").classList.toggle("clock-bad",next.clock?.status!=="qualified");$("journey-export").disabled=false;
    recordingId=next.recording?.id || recordingId;$("journey-record").textContent=next.recording ? `Stop recording · ${next.recording.frame_count} frames` : "Record observations";
    drawPaths();recentActions();V.boundaries(next);renderLab(next.lab);mode();
  }
  async function refresh(manual=false) {
    clearTimeout(timer);if(recording || busy || (paused && !manual))return;busy=true;mode();
    try {const next=await request("/journey/snapshot"+(selectedNamespace ? "?namespace="+encodeURIComponent(selectedNamespace) : ""));if(recording)return;stale=false;$("journey-updated").classList.remove("stale-label");render(next);$("journey-error").hidden=true;
      if(next.unavailable?.length)error(`Some observations are unavailable: ${next.unavailable.join(", ")}. Their values remain unmeasured.`);
      if(trace)await loadTrace(trace.kind,trace.id);
    }catch(e){stale=true;error(`${data ? "Displayed observations are stale; their original timestamps are retained. " : "No live observations yet. "}${e.message}. Start .\\start-failure-demo.ps1 after the prototype, or open saved JSON evidence.`);$("journey-updated").classList.add("stale-label");}
    finally{busy=false;mode();if(!recording && !paused && !document.hidden)timer=setTimeout(refresh,5000);}
  }
  function download(value,name){const url=URL.createObjectURL(new Blob([json(value)],{type:"application/json"})),a=n("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function listRecordings() {
    if(recording)return;try{const value=await request("/journey/recordings");$("recording-select").replaceChildren(n("option","Choose a recording"));$("recording-select").firstChild.value="";for(const saved of value.recordings){const option=n("option",`${stamp(saved.started_at)} · ${saved.frame_count} frames · ${saved.status}`);option.value=saved.id;$("recording-select").append(option);}$("recording-state").textContent=value.recordings.length ? "Open a saved observation run; playback disables all fixture controls." : "No recorded frames yet. Record a real run or open an exported observation file.";}catch(e){$("recording-state").textContent=`Saved-run list unavailable. Local JSON evidence still opens without services. ${e.message}`;}
  }
  function showFrame(index) {
    frame=Math.max(0,Math.min(recording.frames.length-1,index));traceSequence++;const old=trace;render(recording.frames[frame]);
    $("playback-position").value=String(frame);$("playback-label").textContent=`Frame ${frame+1} / ${recording.frames.length} · observed ${stamp(data.observed_at)}`;
    if(old){trace={...old,events:M.related(data.events,old.kind,old.id),visibility:data.selected_trace?.id===old.id ? data.selected_trace.visibility : null,business_result:data.selected_trace?.id===old.id ? data.selected_trace.business_result : null,timelines:null};eventKey=trace.events.some(e=>e.key===eventKey) ? eventKey : trace.events[0]?.key;traceGraph();if(eventKey)inspect(eventKey);}
  }
  function openPlayback(value) {
    const parsed=M.recording(value);recording=parsed;clearTimeout(timer);clearTimeout(playTimer);playing=false;traceSequence++;
    $("playback-bar").hidden=false;$("playback-position").max=String(parsed.frames.length-1);$("playback-play").textContent="Play observations";
    $("recording-state").textContent=`Saved run ${parsed.id || "imported"} · ${parsed.frames.length} frames · ${parsed.integrity || "imported evidence"}. Playback performs no network mutations.`;$("journey-error").hidden=true;showFrame(0);
  }
  function tick() {
    if(!playing || !recording)return;
    if(frame>=recording.frames.length-1){playing=false;$("playback-play").textContent="Play observations";return;}
    const gap=M.elapsed(recording.frames[frame].observed_at,recording.frames[frame+1].observed_at),delay=Math.min(30000,Math.max(100,(gap ?? 1000)/Number($("playback-speed").value)));
    playTimer=setTimeout(()=>{showFrame(frame+1);tick();},delay);
  }
  $("trace-form").addEventListener("submit",e=>{e.preventDefault();loadTrace($("trace-kind").value,$("trace-id").value.trim());});
  $("recent-actions").addEventListener("change",()=>{const [kind,id]=$("recent-actions").value.split(":");if(id)loadTrace(kind,id);});
  $("projection-stage").addEventListener("click",()=>selectStage("projection"));
  $("copy-event-id").addEventListener("click",()=>{const id=trace?.events.find(e=>e.key===eventKey)?.event_id;if(id)navigator.clipboard?.writeText(id).catch(()=>error("Clipboard unavailable. The event ID is visible in the inspector."));});
  $("journey-pause").addEventListener("click",()=>{paused=!paused;clearTimeout(timer);mode();if(!paused)refresh();});
  $("journey-refresh").addEventListener("click",()=>refresh(true));
  $("journey-export").addEventListener("click",()=>{if(data)download({...data,selected_trace:trace},`data-journey-${data.namespace}-${Date.now()}.json`);});
  $("journey-record").addEventListener("click",async()=>{if(recording)return;try{if(data?.recording){const result=await request("/journey/recordings/stop",{method:"POST"});recordingId=result?.id;$("recording-state").textContent=`Saved observation recording ${recordingId}.`;}else{const result=await request("/journey/recordings/start"+(selectedNamespace ? "?namespace="+encodeURIComponent(selectedNamespace) : ""),{method:"POST"});recordingId=result.id;}await refresh(true);await listRecordings();}catch(e){error(e.message);}});
  $("namespace-select").addEventListener("change",()=>{if(recording)return;selectedNamespace=$("namespace-select").value;traceSequence++;trace=null;eventKey=null;traceGraph();refresh(true);});
  $("lab-consent").addEventListener("change",mode);
  $("lab-start").addEventListener("click",async()=>{if(recording || !selectedScenario || !$("lab-consent").checked)return;$("lab-start").disabled=true;try{renderLab(await request("/journey/lab/start",{method:"POST",body:JSON.stringify({scenario:selectedScenario,confirmed:true})}));$("lab-consent").checked=false;}catch(e){error(e.message);}finally{mode();}});
  $("lab-recover").addEventListener("click",async()=>{if(recording || !labRun)return;try{renderLab(await request(`/journey/lab/${labRun.id}/recover`,{method:"POST"}));}catch(e){error(e.message);}});
  $("lab-export").addEventListener("click",()=>{if(labRun)download(labRun,`edge-lab-${labRun.id}.json`);});
  $("recordings-refresh").addEventListener("click",listRecordings);
  $("open-recording").addEventListener("click",async()=>{const id=$("recording-select").value;if(!id || recording)return;try{openPlayback(await request(`/journey/recordings/${id}`));}catch(e){error(e.message);}});
  $("evidence-file").addEventListener("change",async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>40*1024*1024)throw new Error("Evidence file exceeds the 40 MiB presentation limit.");openPlayback(JSON.parse(await file.text()));}catch(errorValue){error(errorValue.message);}finally{e.target.value="";}});
  $("playback-position").addEventListener("input",()=>{clearTimeout(playTimer);playing=false;$("playback-play").textContent="Play observations";showFrame(Number($("playback-position").value));});
  $("playback-play").addEventListener("click",()=>{if(!recording)return;playing=!playing;clearTimeout(playTimer);if(playing && frame===recording.frames.length-1)showFrame(0);$("playback-play").textContent=playing ? "Pause playback" : "Play observations";tick();});
  $("back-live").addEventListener("click",()=>{recording=null;playing=false;data=null;clearTimeout(playTimer);$("playback-bar").hidden=true;trace=null;eventKey=null;paused=false;mode();refresh();});
  document.addEventListener("visibilitychange",()=>{clearTimeout(timer);if(!document.hidden && !paused && !recording)refresh();});
  scenarioCards();drawPaths();mode();refresh();listRecordings();
})();
