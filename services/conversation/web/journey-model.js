"use strict";
(function(root) {
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const time = value => typeof value === "string" && /(?:Z|\+00:00)$/.test(value) && Number.isFinite(Date.parse(value)) ? Date.parse(value) : null;
  const elapsed = (start,end) => { const a=time(start),b=time(end);return a===null || b===null || b<a ? null : b-a; };
  function related(events,kind,id) {
    const field={order:"order_id",search:"search_id",event:"event_id"}[kind];
    const direct=events.filter(e=>(kind==="event" ? e : e.payload || {})[field]===id || e.aggregate_id===id);
    const values=key=>new Set(direct.map(e=>e.payload?.[key]).filter(Boolean));
    const orders=values("order_id"),searches=values("search_id"),turns=values("turn_id");
    return events.filter(e=>direct.includes(e) || orders.has(e.payload?.order_id) || searches.has(e.payload?.search_id) || turns.has(e.payload?.turn_id));
  }
  function timeline(event,clock={}) {
    const r=event.receipt || {}, values=[
      ["request","Request submitted",event.request_submitted_at], ["producer","Producer / outbox",event.produced_at],
      ["kafka","Kafka observed",event.kafka_observed_at || r.ingested_at], ["bronze","Bronze durable",r.bronze_durable_at],
      ["silver","Silver commit observed",r.silver_committed_observed_at], ["gold","Active Gold visible",r.gold_visible_at]];
    let previous=null;
    return values.map(([key,label,at])=>{
      let status=time(at)!==null ? "observed" : "unavailable";
      if(key==="gold" && r.disposition==="invalid") status="failed";
      else if(key==="gold" && !at && r.disposition) status="pending";
      else if(!at && event.outbox_pending && ["kafka","bronze","silver"].includes(key)) status="pending";
      const duration=elapsed(previous,at),ordering=previous && at && duration===null ? "invalid_clock_order" : null;
      if(at) previous=at;
      const qualified=clock.status==="qualified" && (!["bronze","silver","gold"].includes(key) || r.timing_validity==="observed");
      return {key,label,at:at || null,status,since_previous_observed_ms:qualified ? duration : null,ordering,
        timing_validity:["bronze","silver","gold"].includes(key) ? r.timing_validity || "missing" : "observed",
        clock_validity:clock.status || "unavailable"};
    });
  }
  function quantiles(values) {
    const sorted=values.filter(finite).sort((a,b)=>a-b),result={sample_count:sorted.length};
    for(const q of [.5,.95,.99]) result[`p${q*100}_ms`]=sorted.length ? sorted[Math.ceil(q*sorted.length)-1] : null;
    return result;
  }
  function latency(events,clock={}) {
    const unique=new Map();
    for(const e of events) if(e.event_id && e.receipt?.disposition!=="invalid") {
      if(!unique.has(e.event_id) || (!unique.get(e.event_id).receipt?.gold_visible_at && e.receipt?.gold_visible_at)) unique.set(e.event_id,e);
    }
    const complete=[...unique.values()].filter(e=>e.receipt?.gold_visible_at),samples=[],scheduled=[],breakdown=[];
    for(const e of complete) {
      const r=e.receipt,qualified=clock.status==="qualified" && r.timing_validity==="observed";
      const duration=elapsed(e.produced_at,r.gold_visible_at),schedule=elapsed(e.scheduled_at,r.gold_visible_at);
      if(qualified && duration!==null) samples.push(duration);
      if(qualified && schedule!==null) scheduled.push(schedule);
      breakdown.push({event_id:e.event_id,event_type:e.event_type,producer_to_gold_ms:qualified ? duration : null,
        relay_to_observation_ms:qualified ? elapsed(e.produced_at,e.kafka_observed_at || r.ingested_at) : null,
        ingestion_ms:qualified ? elapsed(r.ingested_at,r.silver_committed_observed_at) : null,
        publication_ms:qualified ? elapsed(r.silver_committed_observed_at,r.gold_visible_at) : null});
    }
    return {producer_to_gold:quantiles(samples),schedule_to_gold:quantiles(scheduled),cohort_count:unique.size,
      completed_count:complete.length,unresolved_count:unique.size-complete.length,breakdown,
      cohort_p99_established:unique.size>0 && (unique.size-complete.length)/unique.size<=.01 && complete.length===samples.length};
  }
  function validateSnapshot(frame) {
    if(!frame || frame.schema!=="journey-snapshot-v1" || !Array.isArray(frame.events) || frame.events.length>5000 || time(frame.observed_at)===null) throw new Error("This file is not a supported observation snapshot.");
    if(frame.events.some(e=>!e || typeof e!=="object" || typeof e.key!=="string")) throw new Error("Invalid observation record.");
    return frame;
  }
  function recording(document) {
    if(document?.schema==="journey-snapshot-v1") return {schema:"journey-observations-v1",id:"imported-snapshot",frames:[validateSnapshot(document)],integrity:"browser_import_not_server_verified"};
    if(document?.schema!=="journey-observations-v1" || !Array.isArray(document.frames) || !document.frames.length || document.frames.length>120) throw new Error("Open a Data Journey recording or exported snapshot. No supported observation frames were found.");
    document.frames.forEach(validateSnapshot);
    return document;
  }
  function workloadRates(run) {
    if(!run?.measurement_window) return {offered_per_second:null,admitted_per_second:null,gold_goodput_per_second:null,
      basis:"No generated-workload schedule in this observation. Interactive visits are not offered traffic."};
    const window=run.measurement_window,seconds=elapsed(window.started_at,window.ended_at)/1000;
    if(!seconds) return {offered_per_second:null,admitted_per_second:null,gold_goodput_per_second:null,basis:"Measurement interval unavailable."};
    const inside=at=>time(at)!==null && time(at)>=time(window.started_at) && time(at)<time(window.ended_at);
    const admitted=(run.emissions || []).filter(e=>inside(e.broker_acked_at)).length;
    const cohort=new Set((run.emissions || []).filter(e=>e.broker_acked_at && e.event_id).map(e=>e.event_id));
    const visible=new Set((run.receipts || []).filter(r=>cohort.has(r.event_id) && r.disposition==="new_valid" && inside(r.gold_visible_at)).map(r=>r.event_id));
    return {offered_per_second:(run.planned_emissions || []).filter(e=>inside(e.scheduled_at)).length/seconds,
      admitted_per_second:admitted/seconds,gold_goodput_per_second:visible.size/seconds,
      basis:`Finite isolated fixture · ${seconds.toFixed(2)} s intended window · Kafka acknowledgements are admission; drain completions excluded from goodput.`};
  }
  const api={finite,time,elapsed,related,timeline,quantiles,latency,recording,validateSnapshot,workloadRates};
  root.JourneyModel=api;
  if(typeof module!=="undefined") module.exports=api;
})(typeof window!=="undefined" ? window : globalThis);
