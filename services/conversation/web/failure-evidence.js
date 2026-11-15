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
  function presentationLog(run) {
    const rows=executionLog(run);
    let lastGold=null;
    return rows.filter(row=>{
      // Readiness probes and unrelated analytics-worker samples obscure the fault story.
      // Keep unavailable transitions: a failed read must never look like success.
      if(row.message==="Observation unavailable"){
        if(row.source==="Active Gold")lastGold=null;
        return true;
      }
      if(row.basis==="observed" && row.source==="Analytics API")return false;
      if(row.basis==="observed" && row.source==="Docker" && run.scenario!=="analytics")return false;
      if(row.source==="Active Gold"){
        const key=JSON.stringify([row.details.match,row.details.order_version]);
        if(lastGold===key)return false;
        lastGold=key;
      }
      return true;
    }).map(row=>{
      if(row.message==="Observation unavailable")return row;
      const d=row.details;
      let message=row.message;
      if(row.source==="Inventory API" && present(d.on_hand))message=`Stock: ${d.on_hand} on hand; ${d.reserved} reserved for pending orders.`;
      if(row.source==="Inventory API" && d.state)message=`Reservation ${d.state}.`;
      if(row.source==="Orders API" && d.status)message=`Order ${d.status} (version ${d.version})${d.failure_code ? ": "+d.failure_code : "."}`;
      if(row.source==="Payments ledger" && present(d.net_amount_minor))message=`Net ledger balance: INR ${(d.net_amount_minor/100).toFixed(2)} (signed debits and reversals).`;
      if(row.basis==="service_record" && d.currency && present(d.amount_minor))message=`${d.kind}: ${d.currency} ${(d.amount_minor/100).toFixed(2)} recorded in the payment ledger.`;
      if(row.source==="Active Gold")message=d.match ? `Gold matches this exact order version (generation ${d.generation}).` : `Order version ${d.order_version} is not yet visible in Gold.`;
      return {...row,message};
    });
  }
  const api={executionLog,presentationLog};
  if(typeof module==="object" && module.exports)module.exports=api;
  else root.FailureEvidence=api;
})(typeof window==="object" ? window : globalThis);
