// Real desktop services; creates a session/cart/quote, never submits checkout.
// Repeated DOM messages below are an explicit layout stress fixture only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
if (process.env.RUN_LAYOUT_BROWSER_LIVE !== '1') {
  console.error('Set RUN_LAYOUT_BROWSER_LIVE=1 for the desktop layout check.');
  process.exit(2);
}
const {chromium} = require(path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out = path.resolve(process.env.BROWSER_EVIDENCE_DIR || `artifacts/layout-browser/${Date.now()}`);
fs.mkdirSync(out, {recursive:true});
const write = (name, value) => fs.writeFileSync(path.join(out,name),JSON.stringify(value,null,2));
(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const page = await browser.newPage({viewport:{width:1366,height:768}});
  const errors=[], purchases=[], checks=[], turns=[];
  page.on('pageerror', e=>errors.push(e.message));
  page.on('request', r=>{if(r.url().endsWith('/checkout')) purchases.push(r.postDataJSON());});
  const settled=()=>page.waitForFunction(()=>!document.body.classList.contains('busy'));
  const geometry = async () => {
    const data = await page.evaluate(() => {
      const rect = selector => {
        const r=document.querySelector(selector).getBoundingClientRect();
        return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};
      };
      return {viewport:{width:innerWidth,height:innerHeight},
        width:document.documentElement.scrollWidth, sidebar:rect('aside.assistant'),
        scroll:rect('.chat-scroll'), composer:rect('.chat-composer'),
        controls:['#more-options','#new-search','#chat-input','#send-chat',
          '#assistant-settings>summary'].map(selector=>({selector,...rect(selector)}))};
    });
    assert(data.width<=data.viewport.width,'Page must not scroll sideways');
    assert(data.scroll.bottom<=data.composer.top+1,'Messages must not overlap the composer');
    for(const c of data.controls) {
      assert(c.width>0 && c.height>0,`${c.selector} has no visible area`);
      assert(c.left>=data.sidebar.left && c.right<=data.sidebar.right,`${c.selector} overflows horizontally`);
      assert(c.top>=0 && c.bottom<=data.viewport.height,`${c.selector} is outside the desktop viewport`);
    }
    for(let i=0;i<data.controls.length;i++) for(let j=i+1;j<data.controls.length;j++) {
      const a=data.controls[i],b=data.controls[j];
      assert(!(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1 &&
        Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1),`${a.selector} overlaps ${b.selector}`);
    }
    checks.push(data);
  };
  try {
    await page.goto('http://127.0.0.1:8001/',{waitUntil:'domcontentloaded'});
    await page.locator('#products .product-card').first().waitFor({timeout:20000});
    await page.waitForFunction(()=>!document.getElementById('send-chat').disabled);
    assert.equal(await page.locator('#retrieval').count(),0);
    assert(!/A real catalogue\. A simulated checkout\.|Historical INR prices/.test(await page.locator('body').innerText()));
    await page.screenshot({path:path.join(out,'welcome.png'),fullPage:true});
    await page.locator('#assistant-settings>summary').click();
    await page.locator('#assistant-mode').selectOption('fixed');
    await page.locator('#assistant-settings>summary').click();
    await page.locator('#chat-input').fill('shirts under 1000 rupees');
    const response=page.waitForResponse(r=>r.url().endsWith('/shopping-turns'));
    await page.locator('#send-chat').click();
    const result=await (await response).json(); turns.push(result); await settled();
    assert.equal(result.outcome,'success',result.response_text);
    assert(result.products.length>0 && result.products.every(p=>p.retrieval_mode==='hybrid_exact'));
    // Stress scrolling with copies of an actual rendered message, without extra API/model calls.
    await page.evaluate(()=>{
      const messages=document.getElementById('messages');
      for(let i=0;i<16;i++) messages.append(messages.lastElementChild.cloneNode(true));
      const scroll=document.querySelector('.chat-scroll'); scroll.scrollTop=scroll.scrollHeight;
    });
    for(const [width,height] of [[1366,768],[1280,720],[1440,900],[1920,1080],[1067,600]]) {
      await page.setViewportSize({width,height}); await page.evaluate(()=>window.scrollTo(0,0));
      await geometry();
      await page.screenshot({path:path.join(out,`chat-${width}x${height}.png`),fullPage:true});
      await page.locator('#assistant-settings>summary').click(); await geometry();
      await page.locator('#assistant-settings>summary').click();
    }
    await page.setViewportSize({width:1366,height:768});
    await page.locator('#search').fill('shirts under 1000 rupees');
    const searchResponse=page.waitForResponse(r=>r.url().includes('/v1/store/products?'));
    await page.locator('#search-form button').click();
    const found=await (await searchResponse).json();
    assert(found.items.length>0 && found.items.every(p=>p.retrieval_mode==='hybrid_exact' && p.price_minor<100000));
    write('browse-search.json',found);
    await page.locator('#products .product-card').first().locator('[data-action=add]').click(); await settled();
    await page.locator('#cart-open').click();
    assert.equal(await page.locator('#request-quote').innerText(),'Review order');
    await page.locator('#request-quote').click(); await settled();
    await page.locator('.quote-total').waitFor();
    assert(await page.locator('#confirm-purchase').isDisabled());
    assert.equal(await page.locator('.quote-box h3').innerText(),'Order summary');
    assert(!/authoritative|cart version|Quote [0-9a-f]/i.test(await page.locator('#cart-dialog').innerText()));
    await page.locator('#review-quote').check();
    assert(await page.locator('#confirm-purchase').isEnabled());
    await page.screenshot({path:path.join(out,'checkout.png'),fullPage:true});
    await page.locator('#cart-dialog [data-close]').click();
    assert.equal(purchases.length,0);
    await page.locator('#search').fill('white shirt');
    const strictResponse=page.waitForResponse(r=>r.url().includes('/v1/store/products?'));
    await page.locator('#search-form button').click();
    const strict=await (await strictResponse).json();
    assert.deepEqual(strict.items,[]); assert.equal(strict.total,0);
    assert.deepEqual(errors,[]);
    write('checks.json',{status:'PASS',desktop_checks:checks,purchases:purchases.length,
      console_errors:errors,layout_stress:'Repeated DOM messages, real APIs for search/cart/quote'});
    write('turns.json',turns);
    console.log('Desktop layout, hybrid search and order review: PASS. Evidence:',out);
  } catch(e) {
    write('failure.json',{message:e.message,stack:e.stack,checks,errors,turns});
    await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});
    throw e;
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
