// Real services and AI; a synthetic stale client record checks safe dataset reconnect.
// No checkout, purchase or fault is submitted.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
if(process.env.RUN_HOME_CONTROLS_LIVE!=='1')process.exit(2);
const {chromium}=require(path.resolve('artifacts/tooling/prototype-browser/node_modules/playwright'));
const out=path.resolve(`artifacts/home-controls-browser/${Date.now()}`);fs.mkdirSync(out,{recursive:true});
const write=(name,value)=>fs.writeFileSync(path.join(out,name),JSON.stringify(value,null,2));
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext({viewport:{width:1440,height:950}}),page=await context.newPage();
  const errors=[],posts=[],turns=[];
  const previous={namespace:'dev',user_id:'synthetic-stale-client',session_id:'10000000-0000-4000-8000-000000000001',cart_id:'old-cart',pending:{label:'checkout',path:'/v1/carts/old-cart/checkout',method:'POST',body:{confirmed:true,confirmation_id:'20000000-0000-4000-8000-000000000001'},headers:{'Idempotency-Key':'stale-identity'}}};
  await page.addInitScript(value=>{if(!sessionStorage.getItem('controls-seeded')){localStorage.setItem('shoptalk-session',JSON.stringify(value));sessionStorage.setItem('controls-seeded','1');}},previous);
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST')posts.push(r.url());});
  const waitProducts=()=>page.waitForResponse(r=>r.url().includes('/v1/store/products?') && r.request().method()==='GET',{timeout:20000});
  async function chat(trigger){const reply=page.waitForResponse(r=>r.url().endsWith('/shopping-turns'),{timeout:40000});reply.catch(()=>{});await trigger();const r=await reply,data=await r.json();assert.equal(r.status(),200);assert.notEqual(data.outcome,'dependency_error',data.response_text);assert(data.response_text);assert.equal(r.request().postDataJSON().mode,'assist');turns.push(data);await page.waitForFunction(()=>!document.body.classList.contains('busy'));return data;}
  try{
    await page.goto('http://127.0.0.1:8001/');
    await page.locator('#products .product-card').first().waitFor({timeout:40000});
    await page.waitForFunction(()=>!document.getElementById('send-chat').disabled);
    assert.equal(await page.locator('#more-options').count(),0);
    assert((await page.locator('#category option').count())>2);
    const stored=await page.evaluate(()=>({active:JSON.parse(localStorage.getItem('shoptalk-session')),archived:JSON.parse(localStorage.getItem('shoptalk-session:dataset:dev'))}));
    assert.notEqual(stored.active.namespace,'dev');assert.deepEqual(stored.archived,previous);assert(!posts.some(p=>p.endsWith('/checkout')));
    const options=await page.locator('#category option').evaluateAll(rows=>rows.map(o=>({value:o.value,label:o.label})).filter(o=>o.value));
    const category=options.find(o=>/watches/i.test(o.label)) || options[0];
    let response=waitProducts();await page.locator('#category').selectOption(category.value);let r=await response,data=await r.json();
    assert.equal(new URL(r.url()).searchParams.get('category'),category.value);assert(data.items.length);assert(data.items.every(p=>p.category===category.value));
    response=waitProducts();await page.locator('#sort').selectOption('price_asc');r=await response;data=await r.json();assert.equal(new URL(r.url()).searchParams.get('sort'),'price_asc');assert(data.items.every((p,i,a)=>!i || p.price_minor>=a[i-1].price_minor));
    response=waitProducts();await page.locator('#budget').fill('1000');await page.locator('#budget').press('Tab');r=await response;data=await r.json();assert.equal(new URL(r.url()).searchParams.get('max_price_minor'),'100000');assert(data.items.every(p=>p.price_minor<=100000));
    await chat(()=>page.locator('[data-prompt="I need a gift"]').click());
    await page.locator('#chat-input').fill('Show shirts under 1000 rupees');
    const first=await chat(()=>page.locator('#chat-input').press('Enter'));assert.equal(first.outcome,'success');assert(first.products.length);assert(first.products.every(p=>p.retrieval_mode==='hybrid_exact'));
    await page.locator('#chat-input').fill('Thank you');const count=posts.length;await page.locator('#chat-input').press('Shift+Enter');assert.equal(posts.length,count);assert((await page.locator('#chat-input').inputValue()).includes('\n'));
    await chat(()=>page.locator('#send-chat').click());
    assert.equal(turns.length,3);assert((await page.locator('#messages .message').count())>=6);
    await page.reload();await page.waitForFunction(()=>!document.getElementById('send-chat').disabled,{},{timeout:35000});assert((await page.locator('#messages .message').count())>=6);
    assert.deepEqual(errors,[]);assert(!posts.some(p=>p.endsWith('/checkout')));
    write('turns.json',turns);write('checks.json',{status:'PASS',stale_session_archived:true,category_change:true,sort_change:true,budget_change:true,enter_submit:true,shift_enter_newline:true,send_click:true,suggestion_click:true,reload:true,purchases:0,page_errors:errors});
    await page.screenshot({path:path.join(out,'home-controls.png'),fullPage:true});console.log('Home controls: PASS. Evidence:',out);
  }catch(error){write('failure.json',{message:error.message,stack:error.stack,errors,posts,turns});await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});throw error;}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
