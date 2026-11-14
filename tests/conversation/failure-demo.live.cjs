// Real local services + Edge. Opt-in authorizes seven labelled simulated purchases.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
if(process.env.RUN_FAILURE_DEMO_LIVE!=='1') process.exit(2);
const {chromium}=require(path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out=path.resolve(process.env.BROWSER_EVIDENCE_DIR || `artifacts/failure-demo-browser/${Date.now()}`);
fs.mkdirSync(out,{recursive:true});const write=(n,v)=>fs.writeFileSync(path.join(out,n),JSON.stringify(v,null,2));
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
  const errors=[],requests=[],results=[],geometry=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().startsWith('http://127.0.0.1:8010/')) requests.push({method:r.method(),url:r.url(),body:r.postData()});});
  const state=async()=>{const r=await page.request.get('http://127.0.0.1:8010/state',{headers:{Origin:'http://127.0.0.1:8001'}});assert.equal(r.status(),200);return r.json();};
  const click=async(id,action)=>{const response=page.waitForResponse(r=>r.url().startsWith('http://127.0.0.1:8010/') && r.url().includes(action) && r.request().method()==='POST');await page.locator('#failure-'+id).click();const result=await response;return {status:result.status(),body:await result.json()};};
  try{
    await page.goto('http://127.0.0.1:8001/dashboard',{waitUntil:'domcontentloaded'});
    await page.locator('#kpis .kpi').first().waitFor({timeout:25000});
    assert.equal(requests.filter(r=>r.method==='POST').length,0,'Page load must not mutate failure controls');
    await page.locator('#failure-demo>summary').click();
    await page.locator('#failure-connect').click();await page.waitForFunction(()=>!document.getElementById('failure-prepare').disabled);
    for(const scenario of ['analytics','retry','decline','crash','late','refund']){
      await page.locator('#failure-scenario').selectOption(scenario);
      if(scenario==='analytics') await page.locator('#failure-mode').selectOption('automated');
      const prepared=await click('prepare','/prepare');assert.equal(prepared.status,200);
      assert.equal(prepared.body.run.triggered,false);assert.equal(prepared.body.run.checkout,undefined);
      await page.waitForFunction(()=>!document.getElementById('failure-consent').checked);
      assert(await page.locator('#failure-trigger').isDisabled());assert(await page.locator('#failure-test').isDisabled());
      await page.locator('#failure-consent').check();
      if(scenario==='retry'){
        const lost=await click('trigger','/trigger');assert.equal(lost.status,504);assert.equal(lost.body.order_id,undefined);
        await page.waitForFunction(()=>!document.getElementById('failure-retry').disabled);
        const saved=(await state()).run;assert(saved.response_lost);assert(saved.commit_ack.order_id);
        await click('retry','/retry');
        await page.waitForFunction(()=>!document.getElementById('failure-verify').disabled);
        const until=Date.now()+90000;
        while(Date.now()<until){await click('verify','/verify');const r=(await state()).run;if(r.status!=='Pending')break;await page.waitForTimeout(1000);}
      }else assert.equal((await click('test','/test')).status,200);
      await page.waitForFunction(()=>['Passed','Failed','Unavailable'].includes(document.getElementById('failure-status').textContent),{},{timeout:180000});
      const r=(await state()).run;write(`${scenario}.json`,r);assert.equal(r.status,'Passed',JSON.stringify(r.checks));
      assert(r.checks.every(c=>c.passed===true));assert.equal(r.fault_active,false);
      await page.waitForFunction(()=>document.querySelectorAll('#failure-stock-chart svg').length===1 && document.querySelectorAll('#failure-ledger-chart svg').length===1);
      assert.equal(await page.locator('#failure-timeline svg').count(),1);
      await page.locator('#failure-demo').screenshot({path:path.join(out,scenario+'.png')});
      results.push({scenario,mode:r.mode,run_id:r.id,order_id:r.order_id,status:r.status});
      await page.waitForFunction(()=>!document.getElementById('failure-prepare').disabled);
    }
    for(const [width,height] of [[1440,1000],[1366,768],[1280,720],[1920,1080],[1067,600],[760,900]]){
      await page.setViewportSize({width,height});const g=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,panels:[...document.querySelectorAll('#failure-demo .panel')].map(e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right};})}));
      assert(g.scroll<=g.width,'Horizontal page overflow');assert(g.panels.every(r=>r.left>=0 && r.right<=g.width+1));geometry.push(g);
    }
    await page.setViewportSize({width:1440,height:1000});
    const download=page.waitForEvent('download');await page.locator('#failure-evidence').click();await(await download).saveAs(path.join(out,'download.json'));
    assert.equal(JSON.parse(fs.readFileSync(path.join(out,'download.json'))).status,'Passed');
    // Manual professor flow: shopping review and confirmation, not the scripted controller checkout.
    const store=await context.newPage();await store.goto('http://127.0.0.1:8001/');
    await store.locator('#products .product-card').first().waitFor({timeout:25000});
    await store.locator('#products .product-card').first().locator('[data-action="add"]').click();
    await store.waitForFunction(()=>!document.body.classList.contains('busy'));
    await page.locator('#failure-scenario').selectOption('analytics');await page.locator('#failure-mode').selectOption('manual');
    assert.equal((await click('prepare','/prepare')).status,200);assert.equal((await click('trigger','/trigger')).status,200);
    await store.locator('#cart-open').click();await store.locator('#request-quote').click();await store.waitForFunction(()=>!document.body.classList.contains('busy'));
    assert(await store.locator('#confirm-purchase').isDisabled());await store.locator('#review-quote').check();
    await store.locator('#confirm-purchase').click();
    await store.waitForFunction(()=>['CONFIRMED','CANCELLED','MANUAL_REVIEW'].includes(JSON.parse(localStorage.getItem('shoptalk-session')).order?.status),{},{timeout:90000});
    const owned=await store.evaluate(()=>JSON.parse(localStorage.getItem('shoptalk-session')));
    await page.locator('#failure-order-id').fill(owned.order_id);assert.equal((await click('watch','/watch/')).status,200);
    assert.equal((await state()).run.pending_proof,true);
    await page.locator('#failure-demo').screenshot({path:path.join(out,'manual-paused.png')});
    await click('recover','/recover');
    const until=Date.now()+90000;while(Date.now()<until){await click('verify','/verify');const r=(await state()).run;if(r.status!=='Pending')break;await page.waitForTimeout(1200);}
    const manual=(await state()).run;write('manual.json',manual);assert.equal(manual.status,'Passed',JSON.stringify(manual.checks));assert.equal(manual.mode,'manual');
    await page.locator('#failure-demo').screenshot({path:path.join(out,'manual-recovered.png')});results.push({scenario:'analytics',mode:'manual',order_id:manual.order_id,status:manual.status});
    const mutations=requests.filter(r=>r.method==='POST').length;
    await page.locator('#failure-connect').click();await page.locator('#refresh').click();
    await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
    await page.reload();await page.locator('#kpis .kpi').first().waitFor();
    assert.equal(requests.filter(r=>r.method==='POST').length,mutations,'Refresh/reload must never purchase, replay or trigger');
    assert.deepEqual(errors,[]);write('checks.json',{status:'PASS',results,geometry,page_errors:errors,refresh_mutations:0});write('controller-http.json',requests);
    console.log('Real failure dashboard browser: PASS. Evidence:',out);
  }catch(e){write('failure.json',{message:e.message,stack:e.stack,errors,results,requests});await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});throw e;}
  finally{const r=await state().catch(()=>null);if(r?.run?.fault_active || r?.run?.status==='Pending')await page.request.post(`http://127.0.0.1:8010/runs/${r.run.id}/recover`,{headers:{Origin:'http://127.0.0.1:8001'},data:{}}).catch(()=>{});await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
