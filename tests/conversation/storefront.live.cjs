// Explicit opt-in: real browser and backend, including one SCRIPTED_SIMULATED_PURCHASE.
// No test provider or payment/fault override is installed in the running services.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
if (process.env.RUN_BROWSER_LIVE !== '1') {
  console.error('Set RUN_BROWSER_LIVE=1 to authorize the local simulated purchase rehearsal.');
  process.exit(2);
}
const {chromium} = require(process.env.PLAYWRIGHT_MODULE ||
  path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out = path.resolve(process.env.BROWSER_EVIDENCE_DIR ||
  `artifacts/browser-rehearsal/${Date.now()}`);
fs.mkdirSync(out,{recursive:true});
const write = (name,data) => fs.writeFileSync(path.join(out,name),JSON.stringify(data,null,2));

(async () => {
  const browser = await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:1000}});
  const page = await context.newPage();
  // This checkout rehearsal selects the deterministic HTTP mode; the UI stays AI-only.
  await page.route('**/shopping-turns',route=>route.continue({postData:JSON.stringify({...route.request().postDataJSON(),mode:'fixed'})}));
  const journal = [], errors = [], checkoutRequests = [];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{
    if (request.url().endsWith('/checkout')) checkoutRequests.push(request.postDataJSON());
  });
  page.on('response',async response=>{
    if (!response.url().startsWith('http://127.0.0.1:8001/v1/')) return;
    if (response.request().method()==='GET' && !response.url().includes('/orders/') && response.status()<400) return;
    try {journal.push({url:response.url(),method:response.request().method(),status:response.status(),body:await response.json()});}
    catch {journal.push({url:response.url(),status:response.status()});}
    write('http.json',journal);
  });
  const state = () => page.evaluate(()=>JSON.parse(localStorage.getItem('shoptalk-session')));
  const settled = () => page.waitForFunction(()=>!document.body.classList.contains('busy'));
  const turn = async text=>{
    await page.locator('#chat-input').fill(text);
    const response = page.waitForResponse(r=>r.url().endsWith('/shopping-turns'));
    await page.locator('#send-chat').click();
    const body = await (await response).json();
    await settled();
    return body;
  };
  try {
    await page.goto('http://127.0.0.1:8001/',{waitUntil:'domcontentloaded'});
    await page.locator('#products .product-card').first().waitFor({timeout:20000});
    const bootstrap = await page.request.get('http://127.0.0.1:8001/v1/store/bootstrap');
    assert.equal((await bootstrap.json()).simulation,true);
    assert.match(await page.locator('#result-count').innerText(),/19,920/);
    assert.equal(await page.locator('#retrieval').count(),0);
    // This regression has no external model dependency. AI dialogue is rehearsed separately.
    assert.equal((await turn('I need a gift')).outcome,'clarification');
    let first = await turn('shirt under 1000 rupees');
    if (first.outcome==='dependency_error') {
      // Exercise the explicit retry UI; do not treat the failed first attempt as a pass.
      await page.locator('#retry-chat').waitFor({state:'visible'});
      const retried = page.waitForResponse(r=>r.url().endsWith('/shopping-turns'));
      await page.locator('#retry-chat').click(); first=await (await retried).json(); await settled();
    }
    assert.equal(first.outcome,'success'); assert.equal(first.products.length,5);
    assert(first.products.every(p=>p.retrieval_mode==='hybrid_exact' && p.price_minor<100000 && !/bra|trouser/i.test(p.title)));
    const beforeReload=(await state()).session_id;
    await page.reload({waitUntil:'domcontentloaded'});
    await page.locator('#results-title').filter({hasText:'Picked for your preferences'}).waitFor();
    assert.equal((await state()).session_id,beforeReload);
    const more=await turn('Show more options');
    assert.equal(more.outcome,'success');
    assert(!more.products.some(p=>first.products.some(old=>p.sku===old.sku)));

    // A completed failure must preserve results and allow a NEW search identity.
    const countBefore=await page.locator('#products .product-card').count();
    await page.route('**/shopping-turns',async route=>{
      const original=await route.fetch(); const body=await original.json();
      await route.fulfill({json:{...body,outcome:'dependency_error',products:[],search_id:null}});
    },{times:1});
    assert.equal((await turn('show more options')).outcome,'dependency_error');
    assert.equal(await page.locator('#products .product-card').count(),countBefore);
    await page.locator('#retry-chat').waitFor({state:'visible'});
    const retry=page.waitForResponse(r=>r.url().endsWith('/shopping-turns'));
    await page.locator('#retry-chat').click(); assert.equal((await (await retry).json()).outcome,'success'); await settled();
    await page.locator('#products .product-card').first().locator('[data-action="detail"]').first().click();
    assert.equal(await page.getByRole('button',{name:'Find similar'}).count(),0);
    await page.locator('#product-dialog [data-close]').click();

    // Lose the cart response AFTER the real mutation commits, then replay its exact identity.
    const cartRequests=[];
    page.on('request',r=>{if(r.method()==='PUT' && r.url().includes('/items/')) cartRequests.push({body:r.postData(),key:r.headers()['idempotency-key']});});
    await page.route('**/v1/carts/*/items/*',async route=>{await route.fetch(); await route.abort('failed');},{times:1});
    await page.locator('#products .product-card').first().locator('[data-action="add"]').click();
    await page.locator('#retry-pending').waitFor({state:'visible'});
    await page.locator('#retry-pending').click(); await settled();
    assert.equal(cartRequests.length,2); assert.deepEqual(cartRequests[0],cartRequests[1]);
    assert.equal((await state()).cart.version,1); assert.equal((await state()).cart.lines[0].quantity,1);
    await page.locator('#cart-open').click(); await page.locator('#request-quote').click(); await settled();
    await page.locator('.quote-total').waitFor();
    assert(await page.locator('#confirm-purchase').isDisabled());
    assert.equal(checkoutRequests.length,0);
    await page.locator('#cart-dialog [data-close]').click();
    await page.reload({waitUntil:'domcontentloaded'});
    await page.locator('#products .product-card').first().waitFor();
    await page.locator('#cart-open').click();
    assert(await page.locator('#confirm-purchase').isDisabled());
    assert.equal(checkoutRequests.length,0);
    await page.locator('#review-quote').check();
    await page.screenshot({path:path.join(out,'quote.png'),fullPage:true});
    const purchaseResponse=page.waitForResponse(r=>r.url().endsWith('/checkout'));
    await page.locator('#confirm-purchase').click();
    assert.equal((await purchaseResponse).status(),202);
    await page.waitForFunction(()=>['CONFIRMED','CANCELLED','MANUAL_REVIEW'].includes(JSON.parse(localStorage.getItem('shoptalk-session')).order?.status),{},{timeout:120000});
    const purchased=await state();
    write('accepted-order.json',{kind:'SCRIPTED_SIMULATED_PURCHASE',...purchased});
    assert(['CONFIRMED','CANCELLED'].includes(purchased.order.status),'Unreconciled order needs investigation');
    await page.locator('#order details').evaluate(e=>{e.open=true;});
    await page.waitForFunction(()=>JSON.parse(localStorage.getItem('shoptalk-session')).pipeline?.status==='visible',{},{timeout:120000});
    assert(await page.locator('#order details').evaluate(e=>e.open),'Processing details should stay open while status refreshes');
    await page.screenshot({path:path.join(out,'order-gold.png'),fullPage:true});
    write('purchase.json',{kind:'SCRIPTED_SIMULATED_PURCHASE',...(await state())});
    const originalOrder=purchased.order_id;
    await page.reload({waitUntil:'domcontentloaded'});
    await page.locator('#products .product-card').first().waitFor();
    await page.locator('#cart-open').click();
    await page.waitForFunction(()=>JSON.parse(localStorage.getItem('shoptalk-session')).order?.status!=='PENDING');
    assert.equal((await state()).order_id,originalOrder); assert.equal(checkoutRequests.length,1);
    assert(checkoutRequests[0].confirmed===true);
    await page.locator('#cart-dialog [data-close]').click();
    await page.locator('.dashboard-link').click();
    await page.locator('#kpis .kpi').first().waitFor();
    const measurements = await page.request.get(`http://127.0.0.1:8001/v1/sessions/${(await state()).session_id}/metrics`, {headers:(await state()).pending?.headers || {
      'X-Namespace':purchased.namespace,'X-User-ID':purchased.user_id,'X-Run-ID':purchased.run_id,
      'X-Correlation-ID':purchased.correlation_id,'X-Request-ID':require('node:crypto').randomUUID(), 'X-Session-ID':purchased.session_id}});
    assert.equal(measurements.status(),200); write('metrics.json',await measurements.json());
    await page.goto('http://127.0.0.1:8001/',{waitUntil:'domcontentloaded'});
    await page.locator('#products .product-card').first().waitFor();
    const strict=await turn('only white ones');
    assert.equal(strict.outcome,'success'); assert(strict.products.every(p=>p.colour==='white' && !/bra|trouser/i.test(p.title)));
    await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});

    assert.deepEqual(errors,[]);
    write('checks.json',{status:'PASS',order_id:originalOrder,order_status:purchased.order.status,
      checkout_count:checkoutRequests.length,console_errors:errors,automated_response_faults:true});
    console.log('Browser/real-services rehearsal: PASS',originalOrder,purchased.order.status,'Evidence:',out);
  } catch(error) {
    write('failure.json',{message:error.message,stack:error.stack,errors});
    await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});
    throw error;
  } finally {await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
