// Real Windows rehearsal. Explicit opt-in includes two isolated simulated purchases.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
if(process.env.RUN_GUIDED_JOURNEY_LIVE!=='1')process.exit(2);
const {chromium}=require(path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out=path.resolve(process.env.BROWSER_EVIDENCE_DIR || `artifacts/journey-guided-browser/${Date.now()}`);fs.mkdirSync(out,{recursive:true});
const write=(name,value)=>fs.writeFileSync(path.join(out,name),JSON.stringify(value,null,2));
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({viewport:{width:1440,height:950}});
  const errors=[],posts=[],results=[],headers={Origin:'http://127.0.0.1:8001'};let active=null;
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push({url:r.url(),body:r.postData()});});
  const get=async url=>{const r=await page.request.get('http://127.0.0.1:8010'+url,{headers,timeout:40000});assert.equal(r.status(),200);return r.json();};
  try{
    await page.goto('http://127.0.0.1:8001/journey');
    await page.waitForFunction(()=>document.getElementById('journey-mode').textContent==='Live',{},{timeout:45000});
    await page.locator('#journey-pause').click();
    assert.equal(posts.length,0,'Page load must only observe');
    assert.equal(await page.locator('#lab-status').innerText(),'Ready');assert(await page.locator('#lab-result').isHidden());
    assert.equal(await page.locator('#namespace-select,#lab-recover,pre').count(),0);
    for(const scenario of ['duplicate','out_of_order','race','late_event','replay','conflict','malformed']){
      await page.waitForFunction(()=>!document.getElementById('lab-scenario').disabled,{},{timeout:20000});
      await page.locator('#lab-scenario').selectOption(scenario);
      assert.equal(await page.locator('#lab-status').innerText(),'Ready');assert(await page.locator('#lab-result').isHidden());
      if(scenario==='race'){assert(await page.locator('#lab-start').isDisabled());await page.locator('#lab-consent').check();}
      else assert(await page.locator('#lab-consent-label').isHidden());
      assert(await page.locator('#lab-start').isEnabled());
      const response=page.waitForResponse(r=>r.url().endsWith('/journey/lab/start') && r.request().method()==='POST');
      await page.locator('#lab-start').click();const started=await response;assert.equal(started.status(),202);active=(await started.json()).run.id;
      await page.waitForFunction(()=>['Passed','Failed','Could not finish'].includes(document.getElementById('lab-status').textContent),{},{timeout:150000});
      const run=await get('/journey/lab/'+active);write(scenario+'.json',run);assert.equal(run.status,'Passed',JSON.stringify({scenario,error:run.error_type,checks:run.checks}));
      assert.equal(await page.locator('#lab-status').innerText(),'Passed');assert(run.checks.every(c=>c.passed===true));
      assert.equal(await page.locator('#lab-checks tr').count(),run.checks.length);
      assert.equal(await page.locator('#lab-inputs tr').count(),scenario==='race' ? run.requests.length : run.emissions.length);
      if(scenario==='out_of_order'){assert.match(await page.locator('#lab-inputs tr').first().innerText(),/stock_version=2/);assert.match(await page.locator('#lab-checks').innerText(),/stock_version=2, available=4/);}
      assert(posts.some(p=>p.url.endsWith(`/journey/lab/${active}/recover`)),'One click must also finish publication');
      if(scenario==='duplicate'){
        const saved=page.waitForEvent('download');await page.locator('#lab-export').click();await(await saved).saveAs(path.join(out,'duplicate-report.json'));assert.equal(JSON.parse(fs.readFileSync(path.join(out,'duplicate-report.json'))).id,active);
        await page.locator('#lab-show-data').click();await page.waitForFunction(()=>!document.getElementById('source-banner').hidden && document.querySelectorAll('.event-button').length>0,{},{timeout:45000});
        assert(!/bench-journey|Namespace/.test(await page.locator('#source-banner').innerText()));
        await page.locator('#store-data').click();await page.waitForFunction(()=>document.getElementById('source-banner').hidden && !document.getElementById('journey-refresh').disabled,{},{timeout:45000});
      }
      results.push({scenario,status:run.status,id:active,checks:run.checks.length});active=null;console.log(scenario+': Passed through guided UI');
    }
    await page.waitForFunction(()=>!document.getElementById('lab-scenario').disabled,{},{timeout:20000});
    await page.locator('#lab-scenario').selectOption('duplicate');assert.equal(await page.locator('#lab-status').innerText(),'Ready');assert(await page.locator('#lab-result').isHidden());
    const history=await get('/journey/lab'),failed=history.history.find(r=>r.status==='Failed');assert(failed,'Retained failed test must stay available in history');
    await page.locator('#lab-history-panel>summary').click();await page.locator('#lab-history').selectOption(failed.id);await page.locator('#lab-history-open').click();
    await page.waitForFunction(()=>document.getElementById('lab-status').textContent==='Could not finish');
    assert(await page.locator('#lab-result').isVisible());assert(!/Some checks failed/.test(await page.locator('#lab-message').innerText()));
    await page.locator('#lab-scenario').selectOption('duplicate');assert.equal(await page.locator('#lab-status').innerText(),'Ready');assert(await page.locator('#lab-result').isHidden());
    await page.locator('#lab-history-panel>summary').click();
    assert.equal(await page.locator('#recordings,#journey-record,#back-live').count(),0);
    for(const width of [1440,1280,1067]){await page.setViewportSize({width,height:950});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
    await page.setViewportSize({width:1440,height:950});await page.screenshot({path:path.join(out,'journey.png'),fullPage:true});
    assert.deepEqual(errors,[]);write('checks.json',{status:'PASS',results,old_result_isolation:true,one_click_tests:true,recording_controls_removed:true,page_errors:errors});console.log('Guided journey: PASS. Evidence:',out);
  }catch(error){write('failure.json',{message:error.message,stack:error.stack,errors,results,active});await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});throw error;}
  finally{if(active)await page.request.post(`http://127.0.0.1:8010/journey/lab/${active}/recover`,{headers}).catch(()=>{});await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
