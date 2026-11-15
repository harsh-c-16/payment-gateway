"use strict";
(function(root){
  const paths={
    duplicate:["Send the same event twice","Detect the duplicate","Count it once"],
    conflict:["Reuse an ID with changed content","Quarantine the conflict","Keep the original"],
    malformed:["Send invalid JSON between valid events","Quarantine bad data","Publish valid neighbors"],
    out_of_order:["Send newer stock, then older stock","Compare versions","Keep newer stock"],
    late_event:["Publish a time window","Receive an older event","Revise its original window"],
    replay:["Read archived events","Rebuild isolated analytics","Compare and repeat safely"],
    race:["Two shoppers request one unit","Reserve stock atomically","Verify one sale"]
  };
  function story(run){
    if(!run)return [];
    const rows=[],labels=new Map();
    const label=id=>{if(!id)return "Invalid record";if(!labels.has(id))labels.set(id,"E"+(labels.size+1));return labels.get(id);};
    const add=(at,title,detail,basis)=>rows.push({at:at || null,title,detail,basis});
    for(const [i,e] of (run.emissions || []).entries()){
      const name=label(e.event_id);
      add(e.broker_acked_at || e.sent_at,`Delivery ${i+1}: ${name}`,e.broker_acked_at ? "Kafka acknowledged this delivery." : "Send recorded; broker acknowledgement unavailable.","Producer record");
    }
    for(const r of run.receipts || []){
      const name=label(r.event_id),kind=r.disposition;
      const titles={new_valid:"Accepted",duplicate_delivery:"Duplicate suppressed",invalid:"Quarantined",redelivery_noop:"Redelivery ignored"};
      // Receipt classification is known when inspected; do not invent its exact time.
      add(kind==="new_valid" ? r.silver_committed_observed_at : null,`${name}: ${titles[kind] || kind || "Handling unavailable"}`,r.reason_code || (kind==="new_valid" ? "Unique event committed to Silver." : "Recorded consumer disposition: "+(kind || "unavailable")),"Consumer receipt");
    }
    for(const [i,r] of (run.requests || []).entries())add(r.acknowledged_at || r.submitted_at,`Checkout ${i+1} submitted`,r.order_id ? "Orders returned a durable order ID." : "Order acknowledgement not observed.","Request record");
    for(const [name,key] of [["Initial Gold window","before_business_result"],["Gold queried","business_result"]]){
      const g=run[key];if(g)add(g.queried_at,name,`Publication ${g.generation ?? "unavailable"}; ${g.rows?.length ?? "unknown"} result rows observed.`,"Analytics API");
    }
    for(const [name,key] of [["Replay completed","first"],["Repeated replay completed","repeated"]]){
      const r=run.replay?.[key];if(r)add(r.completed_at,name,`Status: ${r.status}. Reconciliation: ${r.reconciliation?.passed===true ? "passed" : "not verified"}.`,"Replay record");
    }
    const timed=rows.filter(r=>Number.isFinite(Date.parse(r.at))).sort((a,b)=>Date.parse(a.at)-Date.parse(b.at));
    const untimed=rows.filter(r=>!Number.isFinite(Date.parse(r.at)));
    const checks=run.checks || [],passed=checks.filter(c=>c.passed===true).length;
    if(checks.length || run.completed_at || run.error_type)add(run.completed_at,"Final verification",`${passed}/${checks.length} checks passed. ${run.status || "Pending"}.`,"Independent checks");
    const final=rows.at(-1)?.title==="Final verification" ? [rows.at(-1)] : [];
    return [...timed,...untimed,...final];
  }
  const api={paths,story};if(typeof module==="object" && module.exports)module.exports=api;else root.PipelineStory=api;
})(typeof window==="object" ? window : globalThis);
