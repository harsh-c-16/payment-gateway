// Desktop rendering checks with explicit HTTP doubles. This is not live pipeline evidence.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out=path.resolve(process.env.BROWSER_EVIDENCE_DIR || `artifacts/journey-browser-double/${Date.now()}`);
fs.mkdirSync(out,{recursive:true});
const write=(name,value)=>fs.writeFileSync(path.join(out,name),JSON.stringify(value,null,2));
const order='a0000000-0000-4000-8000-000000000001',eid='b0000000-0000-4000-8000-000000000001';
const events=['orders','inventory','payments'].map((source_service,i)=>({key:`demo.order-events.v1:0:${i}`,event_id:i ? `b0000000-0000-4000-8000-00000000000${i+1}` : eid,
  namespace:'demo',event_type:i===1 ? 'STOCK_UPDATED' : i===2 ? 'PAYMENT_AUTHORIZED' : 'ORDER_CONFIRMED',source_service,
  aggregate_id:order,aggregate_version:1,produced_at:'2026-11-14T00:00:00Z',payload:{order_id:order},
  receipt:{disposition:'new_valid',timing_validity:'observed',ingested_at:'2026-11-14T00:00:00.100Z',bronze_durable_at:'2026-11-14T00:00:00.200Z',silver_committed_observed_at:'2026-11-14T00:00:00.300Z',gold_visible_at:'2026-11-14T00:00:00.900Z',visibility_generation:2,raw_sha256:'a'.repeat(64),source:{topic:'demo.order-events.v1',partition:0,offset:i,raw_locator:`bronze/example.jsonl#${i}`}}
}));
const snapshot={schema:'journey-snapshot-v1',namespace:'demo',observed_at:'2026-11-14T00:00:01Z',events,
  clock:{status:'qualified',error_bound_ms:5},catalogue:{source:{archive_verified:false},normalization:{canonical_rows:1}},
  outboxes:['conversation','catalog','orders','inventory','payments'].map(service=>({service,pending:0,status:'observed',observed_at:'2026-11-14T00:00:01Z'})),
  pending_gold:{count:0,status:'observed'},manifests:{gold:{generation:2,created_at:'2026-11-14T00:00:00.900Z'}},
  infrastructure:{resources:[],lag:['conversation','retrieval','order','inventory','payment'].map(d=>({group:'demo.analytics.v1',topic:`demo.${d}-events.v1`,partition:0,lag:0}))},unavailable:[]};
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],requests=[],geometry=[];
  let stale=false;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://127.0.0.1:8001/**',async route=>{
    const url=new URL(route.request().url()),relative=url.pathname==='/journey' ? 'journey.html' : url.pathname.replace(/^\/assets\//,'');
    const file=path.resolve('services/conversation/web',relative);
    assert(file.startsWith(path.resolve('services/conversation/web')+path.sep));
    const ext=path.extname(file),type={'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml'}[ext];
    await route.fulfill({status:fs.existsSync(file) ? 200 : 404,contentType:type,body:fs.existsSync(file) ? fs.readFileSync(file) : ''});
  });
  await page.route('http://127.0.0.1:8010/**',async route=>{
    const r=route.request(),url=new URL(r.url());requests.push({path:url.pathname,method:r.method()});
    const headers={'Access-Control-Allow-Origin':'http://127.0.0.1:8001','Access-Control-Allow-Headers':'content-type','Access-Control-Allow-Methods':'GET, POST'};
    if(r.method()==='OPTIONS')return route.fulfill({status:204,headers});
    assert.equal(r.method(),'GET','Observation or playback must not mutate');
    if(stale && url.pathname.endsWith('/snapshot'))return route.abort();
    const value=url.pathname.endsWith('/snapshot') ? snapshot : url.pathname.endsWith('/trace') ? {
      kind:url.searchParams.get('kind'),id:url.searchParams.get('id'),events,observed_at:snapshot.observed_at,
      visibility:{generation:2,queryable:true,visible_event_ids:events.map(e=>e.event_id)},business_result:{table:'order_fact',generation:2,rows:[{order_id:order}]}
    } : {recordings:[]};
    await route.fulfill({json:value,headers});
  });
  try{
    await page.goto('http://127.0.0.1:8001/journey');
    await page.waitForFunction(()=>document.getElementById('journey-mode').textContent==='Live');
    await page.locator('#journey-pause').click();
    assert.equal(await page.locator('[data-stage="archive"]').getAttribute('class').then(s=>s.includes('failed')),true);
    assert.match(await page.locator('[data-stage="queries"]').innerText(),/No query yet/);
    await page.locator('#recent-actions').selectOption(`order:${order}`);
    await page.locator('.service-lane').nth(2).waitFor();
    assert.equal(await page.locator('.event-button').count(),3);
    assert.equal(await page.locator('#action-timeline li').count(),6);
    await page.locator('.record-inspector details>summary').click();
    assert.match(await page.locator('#record-fields').innerText(),/bronze\/example/);
    assert.match(await page.locator('[data-stage="queries"]').innerText(),/Queried generation 2/);
    for(const width of [1440,1366,1280,1067,760]){
      await page.setViewportSize({width,height:900});
      const g=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
      assert(g.scroll<=g.width,JSON.stringify(g));geometry.push(g);
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:path.join(out,'journey-desktop.png'),fullPage:true});
    stale=true;await page.locator('#journey-refresh').click();
    await page.waitForFunction(()=>document.getElementById('journey-mode').textContent==='Unavailable / stale');
    stale=false;await page.locator('#journey-refresh').click();
    await page.waitForFunction(()=>document.getElementById('journey-mode').textContent==='Paused');
    assert.equal(await page.locator('#recordings,#journey-record,#back-live,#evidence-file').count(),0);
    await page.locator('#lab-scenario').selectOption('race');
    assert(await page.locator('#lab-start').isDisabled());
    await page.locator('#lab-consent').check();
    assert(await page.locator('#lab-start').isEnabled());
    assert.deepEqual(errors,[]);
    write('checks.json',{status:'PASS',mode:'explicit_http_doubles',geometry,page_errors:errors,mutations:0,recording_controls_removed:true});
    console.log('Data Journey desktop rendering: PASS (explicit HTTP doubles). Evidence:',out);
  }catch(error){write('failure.json',{message:error.message,stack:error.stack,errors,requests});await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});throw error;}
  finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
