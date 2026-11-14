// Explicit real-service desktop dashboard check; no checkout requests or fault injection.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
if (process.env.RUN_DASHBOARD_BROWSER_LIVE !== '1') process.exit(2);
const {chromium}=require(path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out=path.resolve(process.env.BROWSER_EVIDENCE_DIR || `artifacts/dashboard-browser/${Date.now()}`);
fs.mkdirSync(out,{recursive:true});
const write=(name,value)=>fs.writeFileSync(path.join(out,name),JSON.stringify(value,null,2));
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  // Select fixed mode through the HTTP contract for this deterministic rehearsal.
  await page.route('**/shopping-turns',route=>route.continue({postData:JSON.stringify({...route.request().postDataJSON(),mode:'fixed'})}));
  const errors=[],purchases=[],snapshots=[],geometry=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error') errors.push(m.text());});
  page.on('request',r=>{if(r.url().endsWith('/checkout')) purchases.push(r.url());});
  page.on('response',async r=>{if(r.url().endsWith('/dashboard') && r.request().method()==='GET' && r.headers()['content-type']?.includes('json')) snapshots.push(await r.json());});
  try {
    await page.goto('http://127.0.0.1:8001/dashboard',{waitUntil:'domcontentloaded'});
    await page.locator('#kpis .kpi').first().waitFor({timeout:25000});
    await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
    await page.locator('#pause').click();
    write('initial-snapshot.json',snapshots.at(-1));
    assert.equal(snapshots.at(-1).services.length,6);
    assert(snapshots.at(-1).pipeline,JSON.stringify(snapshots.at(-1).unavailable));
    assert(snapshots.at(-1).receipt_sample);
    assert.equal(snapshots.at(-1).datasets.length,2);
    for(const [width,height] of [[1440,1000],[1366,768],[1280,720],[1920,1080],[1067,600]]) {
      await page.setViewportSize({width,height});
      const sizes=await page.evaluate(()=>({viewport:innerWidth,page:document.documentElement.scrollWidth,
        panels:[...document.querySelectorAll('.panel')].map(e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right};})}));
      assert(sizes.page<=sizes.viewport,'Dashboard must not scroll horizontally');
      assert(sizes.panels.every(r=>r.left>=0 && r.right<=sizes.viewport+1),'Panel exceeds the viewport');
      geometry.push({width,height,...sizes});
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:path.join(out,'dashboard-empty-session.png'),fullPage:true});
    const download=page.waitForEvent('download');await page.locator('#export').click();
    await (await download).saveAs(path.join(out,'export.json'));
    assert.equal(JSON.parse(fs.readFileSync(path.join(out,'export.json'))).namespace,snapshots.at(-1).namespace);
    await page.goto('http://127.0.0.1:8001/',{waitUntil:'domcontentloaded'});
    await page.locator('#products .product-card').first().waitFor();
    assert.equal(await page.locator('#demo-metrics').count(),0);
    await page.locator('#chat-input').fill('shirts under 1000 rupees');
    const turn=page.waitForResponse(r=>r.url().endsWith('/shopping-turns'));
    await page.locator('#send-chat').click();
    const response=await (await turn).json();
    assert.equal(response.outcome,'success',response.response_text);
    await page.waitForFunction(()=>!document.body.classList.contains('busy'));
    await page.locator('.dashboard-link').click();
    await page.locator('#kpis .kpi').first().waitFor();
    await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
    await page.locator('#pause').click();
    const current=snapshots.at(-1);write('snapshot.json',current);
    assert.equal(current.session.sampled_turns,1);
    assert.equal(current.session.searches,1);
    assert.equal(current.session.model_attempts,0);
    assert.equal(current.activity.turns.length,1);
    assert(current.receipt_sample.count<=current.receipt_sample.journal_observations);
    assert.equal(Object.values(current.receipt_sample.dispositions).reduce((sum,n)=>sum+n,0),current.receipt_sample.count);
    const sources=current.receipt_sample.rows.map(r=>`${r.source.topic}:${r.source.partition}:${r.source.offset}`);
    assert.equal(new Set(sources).size,sources.length,'Receipt rows must contain unique source positions');
    assert.equal(await page.locator('#latency-chart svg').count(),1);
    assert.equal(await page.locator('#throughput-chart svg').count(),1);
    assert.equal(await page.locator('#coverage .coverage-card').count(),4);
    await page.screenshot({path:path.join(out,'dashboard-desktop.png'),fullPage:true});
    // Refreshing the analytics page only observes the existing saved turn.
    await page.locator('#refresh').click();
    await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
    assert.equal(snapshots.at(-1).session.sampled_turns,1);
    // Explicit browser-only partial-provider projection; no live service is faulted.
    await page.route('**/v1/sessions/*/dashboard',async route=>{
      const actual=await (await route.fetch()).json();
      await route.fulfill({json:{...actual,pipeline:null,orders:null,receipt_sample:null,
        datasets:[],catalogue:null,unavailable:['pipeline','orders','receipts','catalogue']}});
    },{times:1});
    await page.locator('#refresh').click();
    await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
    assert.equal(await page.locator('#live-status').innerText(),'Paused');
    assert.match(await page.locator('#error').innerText(),/services could not be read/);
    assert.equal(await page.locator('#throughput-chart svg').count(),0);
    assert.match(await page.locator('#kpis .kpi').first().innerText(),/Unavailable/);
    await page.screenshot({path:path.join(out,'partial-data-ui-double.png'),fullPage:true});
    assert.deepEqual(errors,[]);assert.equal(purchases.length,0);
    write('checks.json',{status:'PASS',geometry,console_errors:errors,purchases:0,
      services:current.services,unavailable:current.unavailable,partial_ui_projection_double:true});
    console.log('Real desktop dashboard: PASS. Evidence:',out);
  } catch(e) {
    write('failure.json',{message:e.message,stack:e.stack,errors,snapshots});
    await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});throw e;
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
