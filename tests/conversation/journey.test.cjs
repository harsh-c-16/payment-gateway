"use strict";
const test=require('node:test');
const assert=require('node:assert/strict');
const M=require('../../services/conversation/web/journey-model.js');
const event=()=>({key:'topic:0:1',event_id:'event',produced_at:'2026-11-14T00:00:00Z',payload:{order_id:'order'},
  receipt:{disposition:'new_valid',timing_validity:'observed',ingested_at:'2026-11-14T00:00:00.100Z',silver_committed_observed_at:'2026-11-14T00:00:00.300Z',gold_visible_at:'2026-11-14T00:00:00.900Z'}});
test('missing/negative UTC timings stay missing',()=>{assert.equal(M.elapsed(null,'2026-11-14T00:00:00Z'),null);assert.equal(M.elapsed('2026-11-14T00:00:01Z','2026-11-14T00:00:00Z'),null);assert.equal(M.elapsed('2026-11-14T00:00:00','2026-11-14T00:00:01Z'),null);});
test('nearest rank quantiles retain samples',()=>{assert.deepEqual(M.quantiles([9,1,3,7,5]),{sample_count:5,p50_ms:5,p95_ms:9,p99_ms:9});assert.equal(M.quantiles([]).p99_ms,null);});
test('branch traversal uses order IDs without correlation fanout',()=>{const a=event(),b={...event(),event_id:'payment'},c={...event(),event_id:'other',payload:{order_id:'unrelated'}};assert.deepEqual(M.related([a,b,c],'order','order'),[a,b]);});
test('logical completion deduplicates deliveries and retains unresolved denominator',()=>{const a=event(),pending={...event(),event_id:'pending',receipt:null};const result=M.latency([a,a,pending],{status:'qualified'});assert.equal(result.completed_count,1);assert.equal(result.unresolved_count,1);assert.equal(result.producer_to_gold.p99_ms,900);assert.equal(result.cohort_p99_established,false);});
test('clock qualification gates quantiles and recovery bounds are excluded',()=>{const a=event();assert.equal(M.latency([a],{status:'unavailable'}).producer_to_gold.sample_count,0);a.receipt.timing_validity='recovery_upper_bound';assert.equal(M.latency([a],{status:'qualified'}).producer_to_gold.sample_count,0);});
test('timeline distinguishes pending, unavailable and quarantine',()=>{const a=event();a.receipt.gold_visible_at=null;assert.equal(M.timeline(a,{})[0].status,'unavailable');assert.equal(M.timeline(a,{}).at(-1).status,'pending');a.receipt.disposition='invalid';assert.equal(M.timeline(a,{}).at(-1).status,'failed');});
test('recordings reject unsupported or empty evidence',()=>{assert.throws(()=>M.recording({frames:[]}));assert.throws(()=>M.recording({schema:'journey-observations-v1',frames:[]}));const frame={schema:'journey-snapshot-v1',observed_at:'2026-11-14T00:00:00Z',events:[event()]};assert.equal(M.recording(frame).frames[0],frame);});
test('offered, admission and within-window Gold goodput use distinct numerators',()=>{const result=M.workloadRates({measurement_window:{started_at:'2026-11-14T00:00:00Z',ended_at:'2026-11-14T00:00:02Z'},planned_emissions:[{scheduled_at:'2026-11-14T00:00:00Z'},{scheduled_at:'2026-11-14T00:00:01Z'}],emissions:[{broker_acked_at:'2026-11-14T00:00:01Z'}],receipts:[{event_id:'a',disposition:'new_valid',gold_visible_at:'2026-11-14T00:00:03Z'}]});assert.equal(result.offered_per_second,1);assert.equal(result.admitted_per_second,.5);assert.equal(result.gold_goodput_per_second,0);});
test('interactive visits have no invented offered rate',()=>{const rates=M.workloadRates(null);assert.equal(rates.offered_per_second,null);assert.equal(rates.admitted_per_second,null);assert.equal(rates.gold_goodput_per_second,null);});

test('pending Gold remains pending before a completed timing sample',()=>{
  const a=event();a.receipt.gold_visible_at=null;a.receipt.timing_validity='missing';
  assert.equal(M.timeline(a,{status:'qualified'}).at(-1).status,'pending');
});
test('timeline withholds unqualified and recovery-bound durations',()=>{
  const a=event();assert.ok(M.timeline(a,{status:'unqualified'}).every(s=>s.since_previous_observed_ms===null));
  a.receipt.timing_validity='recovery_upper_bound';
  assert.equal(M.timeline(a,{status:'qualified'}).at(-1).since_previous_observed_ms,null);
});
test('within-window Gold goodput excludes unrelated IDs and duplicate deliveries',()=>{
  const at='2026-11-14T00:00:01Z',result=M.workloadRates({
    measurement_window:{started_at:'2026-11-14T00:00:00Z',ended_at:'2026-11-14T00:00:02Z'},
    emissions:[{event_id:'a',broker_acked_at:at}],
    receipts:['a','a','unrelated'].map(event_id=>({event_id,disposition:'new_valid',gold_visible_at:at}))
  });
  assert.equal(result.gold_goodput_per_second,.5);
});
