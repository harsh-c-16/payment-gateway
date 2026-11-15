// Real browser/controller/owner services; explicitly authorizes one simulated checkout.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
if(process.env.RUN_FAILURE_BROWSER_LIVE!=='1' || process.env.SIMULATE_PURCHASES!=='1')process.exit(2);
const {chromium}=require(path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out=path.resolve(`artifacts/failure-execution-browser/${Date.now()}`);
fs.mkdirSync(out,{recursive:true});
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[],states=[],testRequests=[];
  let runId=null;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().match(/8010\/runs\/[^/]+\/test$/) && r.method()==='POST')testRequests.push(r.postDataJSON());});
  page.on('response',async r=>{if(r.url()==='http://127.0.0.1:8010/state' && r.ok())states.push(await r.json());});
  try{
    await page.goto('http://127.0.0.1:8001/dashboard',{waitUntil:'domcontentloaded'});
    await page.locator('#failure-demo').evaluate(e=>e.open=true);
    await page.waitForFunction(()=>document.getElementById('failure-connection').textContent.includes('Local controller connected'));
    await page.locator('#failure-scenario').selectOption('analytics');
    assert.equal(await page.locator('#failure-test,#failure-trigger').count(),0);
    assert(await page.locator('#failure-prepare').isDisabled());
    await page.locator('#failure-consent').check();
    assert(await page.locator('#failure-journal').isVisible());
    assert(await page.locator('#failure-checks').isVisible());
    assert.equal(await page.locator('#failure-observations').evaluate(e=>e.open),false);
    // One explicit browser-only provider failure verifies that Prepare errors are visible.
    const failPrepare=async route=>{
      if(route.request().method()!=='POST')return route.continue();
      await route.fulfill({status:503,headers:{'Access-Control-Allow-Origin':'http://127.0.0.1:8001'},
        json:{detail:'Explicit UI test: baseline provider unavailable'}});
      await page.unroute('http://127.0.0.1:8010/prepare',failPrepare);
    };
    await page.route('http://127.0.0.1:8010/prepare',failPrepare);
    await page.locator('#failure-prepare').click();
    await page.locator('#failure-error').waitFor({state:'visible'});
    assert.match(await page.locator('#failure-error').innerText(),/baseline provider unavailable/);
    await page.waitForFunction(()=>!document.getElementById('failure-prepare').disabled);
    const prepared=page.waitForResponse(r=>r.url()==='http://127.0.0.1:8010/prepare' && r.request().method()==='POST');
    await page.locator('#failure-prepare').click();
    const response=await prepared;
    assert(response.ok(),await response.text());
    const initial=await response.json();runId=initial.run.id;
    await page.waitForFunction(()=>document.getElementById('failure-status').textContent==='Pending' || document.getElementById('failure-status').textContent==='Passed');
    assert.match(await page.locator('#failure-journal').innerText(),/Baseline captured/);
    await page.waitForFunction(()=>['Passed','Failed','Unavailable'].includes(document.getElementById('failure-status').textContent),null,{timeout:180000});
    assert.equal(await page.locator('#failure-status').innerText(),'Passed',await page.locator('#failure-message').innerText());
    assert.equal(testRequests.length,1,'Exactly one explicit test trigger');
    assert.equal(testRequests[0].confirmed,true);
    const log=await page.locator('#failure-journal').innerText();
    for(const text of ['Analytics worker paused','Checkout acknowledgement','CONFIRMED','Analytics worker resumed','Gold matches this exact order version'])assert(log.includes(text),text);
    assert.equal(await page.locator('#failure-checks .fail').count(),0);
    assert(await page.locator('#failure-checks .pass').count()>=14);
    // Completed result refresh must remain a read and retain the original execution log.
    await page.locator('#failure-connect').click();
    assert.equal(testRequests.length,1);
    const data=await page.evaluate(async()=>await (await fetch('http://127.0.0.1:8010/state')).json());
    assert.equal(data.run.id,runId);
    assert.equal(data.run.pending_proof,true);
    assert.equal(data.run.fault_active,false);
    assert.equal(data.run.publication.status,'visible');
    for(const width of [1440,1067,760]){
      await page.setViewportSize({width,height:1000});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Horizontal overflow');
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:path.join(out,'failure-execution.png'),fullPage:true});
    fs.writeFileSync(path.join(out,'evidence.json'),JSON.stringify(data.run,null,2));
    fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({status:'PASS',runId,
      stateReads:states.length,testRequests:testRequests.length,pageErrors:errors,
      prepareErrorUIProjection:true,logEntries:await page.locator('#failure-journal li').count()},null,2));
    assert.deepEqual(errors,[]);
    console.log('Real analytics failure, recovery and visible execution log: PASS. Evidence:',out);
  }catch(e){
    fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({message:e.message,errors,runId,states},null,2));
    await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});
    if(runId)await page.evaluate(async id=>{
      const state=await (await fetch('http://127.0.0.1:8010/state')).json();
      if(state.run?.id===id && state.run.fault_active && !state.run.test_running)
        await fetch(`http://127.0.0.1:8010/runs/${id}/recover`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{"confirmed":true}'});
    },runId).catch(()=>{});
    throw e;
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
