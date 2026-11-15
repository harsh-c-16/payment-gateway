// Live Windows services plus two browser network faults and one labelled partial UI projection.
// This checks automatic reconnection; it does not inject a service fault or purchase.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
if(process.env.RUN_DASHBOARD_BROWSER_LIVE!=='1')process.exit(2);
const {chromium}=require(path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out=path.resolve(`artifacts/dashboard-helper-browser/${Date.now()}`);
fs.mkdirSync(out,{recursive:true});
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[],mutations=[],infrastructure=[];
  let stateReads=0;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST' && !r.url().endsWith('/v1/sessions'))mutations.push(r.url());});
  page.on('response',async r=>{
    if(r.url()==='http://127.0.0.1:8010/infrastructure' && r.ok())infrastructure.push(await r.json());
  });
  if(process.env.DASHBOARD_ACTIVITY_FILE){
    const activity=JSON.parse(fs.readFileSync(process.env.DASHBOARD_ACTIVITY_FILE,'utf8'));
    assert.equal(activity.status,'PASS');
    await page.addInitScript(state=>localStorage.setItem('shoptalk-session',JSON.stringify(state)),{
      ...activity.identity,cart_id:activity.cart_id
    });
  }
  await page.route('http://127.0.0.1:8010/state',route=>{
    stateReads++;
    return stateReads<=2 ? route.abort() : route.continue();
  });
  try{
    await page.goto('http://127.0.0.1:8001/dashboard',{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.getElementById('failure-connection').textContent.includes('Local controller connected'),{timeout:30000});
    assert(stateReads>=3,'Connection must recover automatically after two browser network failures');
    await page.waitForFunction(()=>document.querySelectorAll('#infra-resources tr').length===12,{timeout:30000});
    await page.waitForFunction(()=>document.querySelector('#infra-lag-chart svg'),{timeout:30000});
    await page.waitForFunction(()=>document.querySelectorAll('#kpis .kpi').length>0,{timeout:30000});
    await page.locator('#failure-demo').evaluate(e=>e.open=true);
    await page.waitForFunction(()=>!document.getElementById('failure-consent').disabled);
    assert(await page.locator('#failure-prepare').isDisabled());
    assert(await page.locator('#failure-prepared-product').isHidden(),'A finished unrelated run must not show a prepared product');
    const infraPanel=page.locator('#pipeline-status');
    await infraPanel.evaluate(e=>e.open=true);
    // A later real snapshot supplies a CPU delta instead of a fabricated first value.
    await page.waitForFunction(()=>[...document.querySelectorAll('#infra-resources tr')].every(r=>!r.textContent.includes('warming up')),{timeout:30000});
    const summary=await page.locator('#infra-lag-summary').innerText();
    assert.match(summary,/records waiting/);
    assert.equal(await page.locator('#infra-lag tr').count(),6);
    // Explicit browser-only projection: one missing partition must not erase measured peers.
    await page.route('http://127.0.0.1:8010/infrastructure',async route=>{
      const response=await route.fetch(),actual=await response.json();
      await route.fulfill({response,json:{...actual,complete:false,
        observation_scope:'explicit_browser_projection',
        lag:actual.lag.map((r,i)=>i ? r : {...r,lag:null,status:'unavailable'})}});
    },{times:1});
    await page.locator('#infra-refresh').click();
    await page.waitForFunction(()=>document.getElementById('infra-lag-summary').textContent.includes('partial total'));
    assert.equal(await page.locator('#infra-lag-chart svg').count(),1);
    await page.screenshot({path:path.join(out,'partial-reading-ui-double.png'),fullPage:true});
    await page.locator('#infra-refresh').click();
    await page.waitForFunction(()=>document.getElementById('infra-lag-summary').textContent.includes('across 6 partitions'));
    for(const width of [1440,1067,760]){
      await page.setViewportSize({width,height:1000});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Horizontal overflow');
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:path.join(out,'dashboard-live.png'),fullPage:true});
    const state=await page.evaluate(()=>({
      controller:document.getElementById('failure-connection').textContent,
      infrastructure:document.getElementById('infra-state').textContent,
      lag:document.getElementById('infra-lag-summary').textContent,
      boundaries:document.getElementById('boundary-cards').textContent,
      kpis:document.getElementById('kpis').textContent,
      errors:document.getElementById('error').textContent
    }));
    assert.deepEqual(errors,[]);
    assert.deepEqual(mutations,[],'Opening and reconnecting must not submit mutations');
    fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({status:'PASS',state,stateReads,
      snapshots:infrastructure,mutations,pageErrors:errors,browserNetworkFaults:2,
      partialReadingUIProjection:true},null,2));
    console.log('Live dashboard and automatic reconnection: PASS. Evidence:',out);
  }catch(e){
    fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({message:e.message,errors,stateReads,mutations},null,2));
    await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});
    throw e;
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
