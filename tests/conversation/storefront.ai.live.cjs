// Real Gemini + real local APIs. Explicit opt-in; no cart or purchase mutations.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
if (process.env.RUN_AI_BROWSER_LIVE !== '1') {
  console.error('Set RUN_AI_BROWSER_LIVE=1 for real Gemini conversation checks.');
  process.exit(2);
}
const {chromium} = require(process.env.PLAYWRIGHT_MODULE ||
  path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out = path.resolve(process.env.BROWSER_EVIDENCE_DIR || `artifacts/ai-browser/${Date.now()}`);
fs.mkdirSync(out,{recursive:true});
const write = (name,value) => fs.writeFileSync(path.join(out,name),JSON.stringify(value,null,2));
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const turns=[],errors=[],purchases=[];
  const state=()=>page.evaluate(()=>JSON.parse(localStorage.getItem('shoptalk-session')));
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().endsWith('/checkout')) purchases.push(r.postDataJSON());});
  const turn=async text=>{
    await page.locator('#chat-input').fill(text);
    const response=page.waitForResponse(r=>r.url().endsWith('/shopping-turns'),{timeout:35000});
    await page.locator('#send-chat').click();
    const r=await response,b=await r.json();
    await page.waitForFunction(()=>!document.body.classList.contains('busy'));
    turns.push({input:text,response:b});write('turns.json',turns);
    assert.equal(r.status(),200);assert.equal(b.llm_call_count,1);
    assert.notEqual(b.outcome,'dependency_error',b.response_text);
    return b;
  };
  try {
    await page.goto('http://127.0.0.1:8001/',{waitUntil:'domcontentloaded'});
    await page.locator('#products .product-card').first().waitFor({timeout:20000});
    assert.equal(await page.locator('#assistant-mode').count(),0);
    assert.equal(await page.locator('#assistant-title').innerText(),'AI conversation');
    assert.equal(await page.locator('#retrieval').count(),0);
    assert.equal((await turn('I need a gift')).outcome,'clarification');
    const first=await turn('A shirt under 1000 rupees');
    assert(first.products.length>0);
    assert(first.products.every(p=>p.retrieval_mode==='hybrid_exact'));
    assert(first.products.every(p=>p.price_minor<100000 && !/bra|trouser/i.test(p.title)));
    const more=await turn('Could you show me a few other choices?');
    assert(more.products.length>1);
    assert(!more.products.some(p=>first.products.some(q=>q.sku===p.sku)));
    const second=more.products[1];
    const detail=await turn('What material is the second one?');
    assert(detail.response_text.includes(second.title));
    assert(detail.response_text.includes(second.material || 'not recorded'));
    const cheaper=await turn('Can I get something cheaper than that?');
    assert(cheaper.products.length>0 && cheaper.products.every(p=>p.price_minor<second.price_minor));
    const strict=await turn('Only white ones');
    assert.equal(strict.intent.colour,'white');
    assert(strict.products.every(p=>p.colour==='white' && !/bra|trouser/i.test(p.title)));
    const before=await state();
    await page.reload({waitUntil:'domcontentloaded'});
    await page.locator('#results-title').filter({hasText:'Picked for your preferences'}).waitFor();
    assert.equal((await state()).session_id,before.session_id);
    assert.equal((await state()).memory.intent.colour,'white');
    assert.equal(await page.locator('#products .product-card').count(),strict.products.length);
    const cleared=await turn('Any colour');
    assert.equal(cleared.intent.colour,null);assert(cleared.products.length>0);
    await turn('Buy it for me');
    assert.equal(purchases.length,0);
    const positions=await page.locator('.message.assistant').evaluateAll(nodes=>nodes.map(n=>getComputedStyle(n).position));
    assert(positions.every(p=>p==='static'),'Chat bubbles must scroll normally, without inheriting the sidebar sticky position');
    await page.locator('.dashboard-link').click();
    await page.locator('#kpis .kpi').first().waitFor();
    const current=await state();
    const headers={'X-Namespace':current.namespace,'X-User-ID':current.user_id,'X-Run-ID':current.run_id,
      'X-Correlation-ID':current.correlation_id,'X-Session-ID':current.session_id,'X-Request-ID':require('node:crypto').randomUUID()};
    const m=await page.request.get(`http://127.0.0.1:8001/v1/sessions/${current.session_id}/metrics`,{headers});
    const metrics=await m.json();write('metrics.json',metrics);
    assert.equal(metrics.model_attempts,turns.length);assert.equal(metrics.sampled_turns,turns.length);
    assert.equal(metrics.dependency_errors,0);assert(metrics.turn_p95_ms>0);
    assert.equal(metrics.pipeline_status,'available');
    assert.deepEqual(errors,[]);
    await page.evaluate(()=>window.scrollTo(0,0));
    await page.screenshot({path:path.join(out,'ai-desktop.png'),fullPage:true});
    write('checks.json',{status:'PASS',session_id:current.session_id,turns:turns.length,purchase_requests:0,console_errors:errors});
    console.log('Real Gemini browser conversation: PASS',current.session_id,'Evidence:',out);
  } catch(e) {
    write('failure.json',{message:e.message,stack:e.stack,console_errors:errors});
    await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});throw e;
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
