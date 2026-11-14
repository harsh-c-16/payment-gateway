// Real Windows Desktop rehearsal. Explicit opt-in authorizes two isolated purchases.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
if(process.env.RUN_JOURNEY_LIVE!=='1')process.exit(2);
const {chromium}=require(path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out=path.resolve(process.env.BROWSER_EVIDENCE_DIR || `artifacts/journey-live/${Date.now()}`);
fs.mkdirSync(out,{recursive:true});const write=(n,v)=>fs.writeFileSync(path.join(out,n),JSON.stringify(v,null,2));
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[],mutations=[],results=[];let active=null,recordingId=null;
  const headers={Origin:'http://127.0.0.1:8001'};
  const get=async path=>{const r=await page.request.get('http://127.0.0.1:8010'+path,{headers,timeout:45000});assert.equal(r.status(),200,await r.text());return r.json();};
  const action=async(id,endpoint)=>{const response=page.waitForResponse(r=>r.url().startsWith('http://127.0.0.1:8010'+endpoint) && r.request().method()==='POST',{timeout:45000});await page.locator('#'+id).click();const r=await response;assert(r.ok(),await r.text());return r.json();};
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST')mutations.push(r.url());});
  try{
    await page.goto('http://127.0.0.1:8001/journey');
    await page.waitForFunction(()=>document.getElementById('journey-mode').textContent==='Live observations',{},{timeout:60000});
    assert.equal(mutations.length,0,'Page load must only observe');
    await page.locator('#journey-pause').click();
    const initial=await get('/journey/snapshot');write('initial.json',initial);
    assert.equal(initial.outboxes.length,5);
    assert(initial.outboxes.every(r=>r.status==='observed'));
    assert(initial.infrastructure.lag?.length>=5);
    assert(initial.catalogue?.source?.archive_verified===true);
    for(const scenario of ['duplicate','conflict','malformed','out_of_order','late_event','replay','race']){
      await page.locator(`[data-scenario="${scenario}"]`).click();
      await page.locator('#lab-consent').check();
      const started=await action('lab-start','/journey/lab/start');active=started.run.id;
      await page.locator('#namespace-select').selectOption(started.run.namespace);
      await page.waitForFunction(()=>!document.getElementById('journey-refresh').disabled);
      await page.locator('#journey-refresh').click();
      await page.waitForFunction(()=>!document.getElementById('journey-refresh').disabled);
      if(scenario==='duplicate'){
        const saved=await action('journey-record','/journey/recordings/start');recordingId=saved.id;
      }
      let run,until=Date.now()+150000;
      while(Date.now()<until){run=await get('/journey/lab/'+active);if(run.status==='Awaiting recovery' || ['Passed','Failed','Unavailable'].includes(run.status))break;await page.waitForTimeout(700);}
      if(run.status==='Awaiting recovery'){
        await page.locator('#journey-refresh').click();await page.waitForFunction(()=>!document.getElementById('journey-refresh').disabled);
        await action('lab-recover',`/journey/lab/${active}/recover`);
      }
      until=Date.now()+150000;
      while(Date.now()<until){run=await get('/journey/lab/'+active);if(['Passed','Failed','Unavailable'].includes(run.status))break;await page.waitForTimeout(700);}
      write(scenario+'.json',run);assert.equal(run.status,'Passed',JSON.stringify({scenario,message:run.message,checks:run.checks}));
      assert(run.checks.length && run.checks.every(c=>c.passed===true));
      const snap=await get('/journey/snapshot?namespace='+run.namespace);write(scenario+'-snapshot.json',snap);
      const event=run.emissions?.find(e=>e.event_id),order=run.requests?.[0]?.order_id;
      if(event || order){
        const kind=order ? 'order' : 'event',id=order || event.event_id;
        const trace=await get(`/journey/trace?kind=${kind}&id=${id}&namespace=${run.namespace}`);write(scenario+'-trace.json',trace);
        assert(trace.events.length);assert(trace.visibility?.queryable);assert(trace.visibility.visible_event_ids.length);
        await page.locator('#trace-kind').selectOption(kind);await page.locator('#trace-id').fill(id);
        const response=page.waitForResponse(r=>r.url().includes('/journey/trace?'));
        await page.locator('#trace-submit').click();assert((await response).ok());
        await page.locator('#action-timeline li').first().waitFor();
        if(scenario==='race')assert(new Set(trace.events.map(e=>e.source_service)).size>=3);
      }
      await page.locator('#edge-lab').screenshot({path:path.join(out,scenario+'.png')});
      if(recordingId && scenario==='duplicate'){
        await action('journey-record','/journey/recordings/stop');
        const saved=await get('/journey/recordings/'+recordingId);assert(saved.frames.length);assert.equal(saved.integrity,'verified_sha256');write('recording.json',saved);
      }
      results.push({scenario,id:active,namespace:run.namespace,status:run.status,checks:run.checks.length});
      active=null;console.log(scenario+': Passed');
      await page.locator('#journey-refresh').click();await page.waitForFunction(()=>!document.getElementById('journey-refresh').disabled);
    }
    const count=mutations.length;
    await page.locator('#evidence-file').setInputFiles(path.join(out,'recording.json'));
    await page.waitForFunction(()=>document.getElementById('journey-mode').textContent==='Saved playback');
    assert(await page.locator('#lab-start').isDisabled());assert(await page.locator('#lab-recover').isDisabled());
    await page.locator('#playback-play').click();await page.waitForTimeout(800);
    assert.equal(mutations.length,count);assert.deepEqual(errors,[]);
    write('checks.json',{status:'PASS',mode:'real_local_services',results,errors,playback_mutations:0});
    console.log('Real Data Journey rehearsal: PASS. Evidence:',out);
  }catch(error){write('failure.json',{message:error.message,stack:error.stack,errors,results,active});await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});throw error;}
  finally{
    if(active)await page.request.post(`http://127.0.0.1:8010/journey/lab/${active}/recover`,{headers}).catch(()=>{});
    if(recordingId)await page.request.post('http://127.0.0.1:8010/journey/recordings/stop',{headers}).catch(()=>{});
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
