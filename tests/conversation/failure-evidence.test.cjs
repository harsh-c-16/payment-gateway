const {test}=require('node:test');
const assert=require('node:assert/strict');
const {executionLog}=require('../../services/conversation/web/failure-evidence.js');
const at=n=>`2026-11-15T10:00:0${n}Z`;

test('missing observations stay missing, while measured zero is retained',()=>{
  assert.deepEqual(executionLog({samples:[{at:at(0),stock_on_hand:null,net_ledger_minor:null}]}),[]);
  const rows=executionLog({samples:[{at:at(1),stock_on_hand:0,stock_reserved:0,net_ledger_minor:0}]});
  assert.equal(rows.length,2);
  assert.equal(rows[0].details.on_hand,0);
  assert.equal(rows[1].details.net_amount_minor,0);
});

test('repeated samples add no transitions and skipped states are never invented',()=>{
  const samples=[{at:at(0),order_status:'CREATED',order_version:1},
    {at:at(1),order_status:'CREATED',order_version:1},
    {at:at(2),order_status:'CANCELLED',order_version:5,order_failure_code:'PAYMENT_DECLINED'}];
  const rows=executionLog({order_id:'order',samples});
  assert.equal(rows.length,2);
  assert.equal(rows[1].at,at(2));
  assert.equal(rows[1].details.failure_code,'PAYMENT_DECLINED');
  assert(!JSON.stringify(rows).includes('PAYMENT_PENDING'));
});

test('only an exact observed Gold match is labelled visible',()=>{
  const rows=executionLog({samples:[{at:at(0),gold_match:null},
    {at:at(1),gold_match:false,order_version:6},
    {at:at(2),gold_match:true,gold_generation:15,order_version:6}]});
  assert.equal(rows.filter(r=>r.source==='Active Gold').length,2);
  assert.match(rows[0].message,/not yet visible/);
  assert.equal(rows[1].details.generation,15);
});

test('no debit or reversal log is invented for a cancellation with an empty ledger',()=>{
  const rows=executionLog({samples:[{at:at(1),net_ledger_minor:0}],audit:{ledger:[]}});
  assert.equal(rows.filter(r=>r.basis==='service_record').length,0);
});

test('ledger records preserve real IDs, timestamps, kind and amount',()=>{
  const rows=executionLog({audit:{ledger:[
    {entry_id:'reversal',payment_id:'pay',order_id:'order',kind:'REVERSAL',amount_minor:500,currency:'INR',created_at:at(2)},
    {entry_id:'debit',payment_id:'pay',order_id:'order',kind:'DEBIT',amount_minor:500,currency:'INR',created_at:at(1)}
  ]}});
  assert.equal(rows[0].details.entry_id,'debit');
  assert.equal(rows[1].details.entry_id,'reversal');
  assert.equal(rows[0].basis,'service_record');
  assert.equal(rows[1].details.payment_id,rows[0].details.payment_id);
});

test('controller details export only allowed fields',()=>{
  const [row]=executionLog({events:[{at:at(0),phase:'Trigger',message:'Pause acknowledged',
    source:'Docker',operation:'pause',target_id:'container',acknowledged:true,INTERNAL_API_TOKEN:'secret'}]});
  assert.equal(row.details.operation,'pause');
  assert(!JSON.stringify(row).includes('secret'));
});

test('worker observation never uses the Orders fault target as the analytics worker ID',()=>{
  const [row]=executionLog({scenario:'crash',target_id:'orders',samples:[{
    at:at(1),worker_paused:false,worker_running:true,worker_container_id:'analytics'}]});
  assert.equal(row.details.target_id,'analytics');
});

test('checkpoint uses its recorded timestamp; absent timestamps stay unavailable',()=>{
  const run={checkpoint:{observed_at:at(1),checkpoint:'saga.after_commit',exit_code:86,order_id:'order'}};
  assert.equal(executionLog(run)[0].at,at(1));
  delete run.checkpoint.observed_at;
  assert.equal(executionLog(run)[0].at,null);
});
