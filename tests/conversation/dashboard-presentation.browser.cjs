// Real local reads using an explicitly supplied session. Never submits a test or purchase.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
if(process.env.RUN_DASHBOARD_BROWSER_LIVE!=='1' || !process.env.DASHBOARD_SESSION_FILE)process.exit(2);
const {chromium}=require(path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out=path.resolve(`artifacts/dashboard-demo/${Date.now()}`);fs.mkdirSync(out,{recursive:true});
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],mutations=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(!['GET','OPTIONS','HEAD'].includes(r.method()))mutations.push(r.url());});
  await page.addInitScript(state=>localStorage.setItem('shoptalk-session',JSON.stringify(state)),JSON.parse(fs.readFileSync(process.env.DASHBOARD_SESSION_FILE,'utf8')));
  try{
    await page.goto('http://127.0.0.1:8001/dashboard',{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelectorAll('#kpis .kpi').length===8 && document.querySelector('#throughput-chart svg'),{timeout:40000});
    await page.waitForFunction(()=>document.querySelector('#infra-lag-chart svg') && document.querySelector('#end-to-end-chart svg'),{timeout:50000});
    const missing=await page.evaluate(()=>{const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);return ids.filter((x,i)=>ids.indexOf(x)!==i);});
    assert.deepEqual(missing,[],'All DOM IDs must be unique');
    assert.equal(await page.locator('#latency-chart svg').count(),1);
    assert.equal(await page.locator('#failure-test,#failure-trigger').count(),0);
    await page.screenshot({path:path.join(out,'overview.png'),fullPage:true});
    await page.locator('#failure-demo').evaluate(e=>e.open=true);
    await page.waitForFunction(()=>document.getElementById('failure-connection').textContent.includes('Local controller connected'));
    assert(await page.locator('#failure-prepare').isDisabled(),'Test requires explicit consent');
    for(const scenario of ['analytics','retry','decline','crash','late','refund']){
      await page.locator('#failure-scenario').selectOption(scenario);
      assert((await page.locator('#failure-concept').innerText()).length>20);
      await page.locator('#failure-consent').check();
      assert(await page.locator('#failure-prepare').isEnabled());
      await page.locator('#failure-consent').uncheck();
    }
    const state=await page.evaluate(async()=>await (await fetch('http://127.0.0.1:8010/state')).json());
    if(state.run){
      await page.locator('#failure-scenario').selectOption(state.run.scenario);
      await page.locator('#failure-connect').click();
      await page.waitForFunction(()=>document.querySelectorAll('#failure-journal .execution-entry').length>0);
      assert((await page.locator('#failure-checks .pass').count())>0);
      await page.locator('#failure-demo').screenshot({path:path.join(out,'recovery-test.png')});
    }
    await page.locator('#pipeline-status').evaluate(e=>e.open=true);
    await page.waitForFunction(()=>document.querySelectorAll('#infra-resources tr').length===12);
    for(const width of [1440,1067,760,390]){
      await page.setViewportSize({width,height:1000});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`No page overflow at ${width}`);
    }
    await page.locator('#failure-demo').evaluate(e=>e.open=false);
    await page.locator('#pipeline-status').evaluate(e=>e.open=false);
    await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    // Explicit browser-only connection fault, never a service mutation.
    await page.route('http://127.0.0.1:8010/infrastructure',route=>route.abort());
    await page.locator('#refresh').click();
    await page.waitForFunction(()=>document.querySelector('[data-source="infrastructure"] .metric-stale'),{timeout:30000});
    await page.unroute('http://127.0.0.1:8010/infrastructure');
    await page.locator('#refresh').click();
    await page.waitForFunction(()=>!document.querySelector('[data-source="infrastructure"] .metric-stale'),{timeout:30000});
    const download=page.waitForEvent('download');await page.locator('#export').click();
    await (await download).saveAs(path.join(out,'dashboard.json'));
    const exported=JSON.parse(fs.readFileSync(path.join(out,'dashboard.json'),'utf8'));
    assert(exported.dashboard_measurements.pipeline.latency.producer_to_gold.sample_count>0);
    assert(exported.dashboard_measurements.infrastructure.lag.length>0);
    assert.equal(exported.dashboard_measurements.stale_sources.length,0);
    assert.deepEqual(errors,[]);assert.deepEqual(mutations,[]);
    fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({status:'PASS',errors,mutations,viewports:[1440,1067,760,390],realSavedRun:state.run?.id,kpis:await page.locator('#kpis').innerText()},null,2));
    console.log('PASS',out);
  }catch(e){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});console.error({errors,mutations});throw e;}
  finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
