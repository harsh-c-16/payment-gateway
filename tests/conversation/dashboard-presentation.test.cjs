const {test}=require('node:test');
const assert=require('node:assert/strict');
const {metrics,recentEvents}=require('../../services/conversation/web/dashboard-presentation.js');
const base=()=>({checked_at:'2026-11-15T10:05:30Z',session:{sampled_turns:0,dependency_errors:0},activity:{turns:[]},pipeline:null});
test('unavailable data is not presented as zero throughput or zero errors',()=>{
  const result=metrics(base());
  assert.equal(result.eventRate,null);assert.equal(result.failures,null);assert.equal(result.retrievalP95,null);
});
test('event rate excludes current partial minute and older minutes',()=>{
  const data=base();data.pipeline={minutes:[
    {minute:'2026-11-15T09:59:00Z',events:900},
    {minute:'2026-11-15T10:00:00Z',events:10},
    {minute:'2026-11-15T10:01:00Z',events:0},
    {minute:'2026-11-15T10:02:00Z',events:5},
    {minute:'2026-11-15T10:03:00Z',events:0},
    {minute:'2026-11-15T10:04:00Z',events:5},
    {minute:'2026-11-15T10:05:00Z',events:900}]};
  const result=metrics(data);assert.equal(result.eventRate,4);assert.equal(result.minuteCount,5);
});
test('retrieval percentile excludes unexecuted searches but retains measured zero',()=>{
  const data=base();data.activity.turns=[{search_executed:false,search_ms:0},
    {search_executed:true,search_ms:0},{search_executed:true,search_ms:250},
    {search_executed:true,search_ms:null}];
  const result=metrics(data);assert.equal(result.retrievalCount,2);assert.equal(result.retrievalP95,250);
});
test('failure rate uses the saved-turn denominator',()=>{
  const data=base();data.session={sampled_turns:20,dependency_errors:2};
  assert.equal(metrics(data).failures,10);
});
test('last-hour pipeline cohort includes pending events and excludes old/future timestamps',()=>{
  const old={produced_at:'2026-11-14T10:00:00Z',receipt:{gold_visible_at:'2026-11-14T10:25:00Z'}};
  const pending={produced_at:'2026-11-15T09:20:00Z',receipt:null};
  const completed={produced_at:'2026-11-15T09:10:00Z',receipt:{gold_visible_at:'2026-11-15T09:10:02Z'}};
  const future={produced_at:'2026-11-15T10:10:00Z'};
  assert.deepEqual(recentEvents({observed_at:'2026-11-15T10:00:00Z',events:[pending,old,completed,future,{produced_at:null}]}),[completed,pending]);
});
