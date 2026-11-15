"use strict";
(function(root) {
  const present=value=>value!==null && value!==undefined;
  const fields=["operation","plan","run_id","target_id","acknowledged","order_id","order_version",
    "request_id","idempotency_key","quote_id","total_amount_minor","backend_committed","injected_status","checkpoint"];
  function executionLog(run) {
    if(!run)return [];
    const rows=[],previous=new Map();
    const add=(at,source,message,details={},basis="observed")=>rows.push({at:at || null,source,message,details,basis});
    for(const event of run.events || []) {
      const details=Object.fromEntries(fields.filter(k=>present(event[k])).map(k=>[k,event[k]]));
      add(event.at,event.source || "Controller",`${event.phase}: ${event.message}`,details,"action");
    }
    function change(sample,key,source,value,message,details) {
      if(!present(value) && !previous.has(key))return;
      const serialized=JSON.stringify(value ?? null);
      if(previous.get(key)===serialized)return;
      previous.set(key,serialized);
      add(sample.at,source,present(value) ? message : "Observation unavailable",details);
    }
    for(const sample of run.samples || []) {
      const worker=present(sample.worker_paused) && present(sample.worker_running)
        ? sample.worker_paused ? "PAUSED" : sample.worker_running ? "RUNNING" : "STOPPED" : null;
      change(sample,"worker","Docker",worker,`Analytics worker observed ${worker}`,{target_id:sample.worker_container_id || (run.scenario==="analytics" ? run.target_id : null),state:worker});
      change(sample,"api","Analytics API",sample.analytics_api_ready,
        `Read API ready=${sample.analytics_api_ready}`,{ready:sample.analytics_api_ready ?? null});
      const order=present(sample.order_status) ? {status:sample.order_status,version:sample.order_version,
        failure_code:sample.order_failure_code ?? null} : null;
      change(sample,"order","Orders API",order,
        `Order ${sample.order_status} / v${sample.order_version}${sample.order_failure_code ? " / "+sample.order_failure_code : ""}`,
        {order_id:run.order_id,...order});
      change(sample,"reservation","Inventory API",sample.reservation_state,
        `Reservation observed ${sample.reservation_state}`,{state:sample.reservation_state ?? null});
      const stock=present(sample.stock_on_hand) && present(sample.stock_reserved)
        ? {on_hand:sample.stock_on_hand,reserved:sample.stock_reserved} : null;
      change(sample,"stock","Inventory API",stock,
        `Stock snapshot: on_hand=${sample.stock_on_hand}, reserved=${sample.stock_reserved}`,stock || {});
      change(sample,"attempts","Payments API",sample.payment_attempts,
        sample.payment_attempts?.length ? sample.payment_attempts.map(a=>`${a.status}${a.failure_code ? " / "+a.failure_code : ""}`).join(", ") : "No payment attempts observed",
        {attempts:sample.payment_attempts ?? null});
      change(sample,"ledger","Payments ledger",sample.net_ledger_minor,
        `Signed net amount observed ${sample.net_ledger_minor} minor units`,{net_amount_minor:sample.net_ledger_minor ?? null});
      const gold=present(sample.gold_match) ? {match:sample.gold_match,generation:sample.gold_generation ?? null,
        order_version:sample.order_version} : null;
      change(sample,"gold","Active Gold",gold,
        sample.gold_match ? `Exact order match visible / generation ${sample.gold_generation}` : "Exact order version not yet visible",
        {order_id:run.order_id,...gold});
    }
    for(const entry of run.audit?.ledger || []) {
      add(entry.created_at,"Payments ledger",`${entry.kind}: ${entry.amount_minor} ${entry.currency} minor units`,
        Object.fromEntries(["entry_id","payment_id","order_id","kind","amount_minor","currency"].map(k=>[k,entry[k] ?? null])),"service_record");
    }
    if(run.retry_ack) add(run.retry_ack.at,"Store API","Retry acknowledged; original request ID, key and body reused",{
      ...run.retry_ack,request_id:run.checkout?.request_id,idempotency_key:run.checkout?.key,same_order:run.retry_same_order
    },"action");
    if(run.checkpoint) add(run.checkpoint.observed_at || run.checkpoint.at || run.checkpoint.created_at,"Orders checkpoint",
      `${run.checkpoint.checkpoint} / process exit ${run.checkpoint.exit_code}`,{
        order_id:run.checkpoint.order_id,exit_code:run.checkpoint.exit_code,checkpoint:run.checkpoint.checkpoint
      },"service_record");
    return rows.map((row,i)=>({...row,index:i})).sort((a,b)=>{
      const at=Date.parse(a.at),bt=Date.parse(b.at);
      return (Number.isFinite(at) ? at : Infinity)-(Number.isFinite(bt) ? bt : Infinity) || a.index-b.index;
    });
  }
  const api={executionLog};
  if(typeof module==="object" && module.exports)module.exports=api;
  else root.FailureEvidence=api;
})(typeof window==="object" ? window : globalThis);
