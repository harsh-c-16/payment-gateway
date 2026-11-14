// Browser-independent controller checks; these do not claim visual browser coverage.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const {randomUUID} = require('node:crypto');

function controller(fetch) {
  const elements = new Map();
  function element() {
    return {checked: false, disabled: false, hidden: false, children: [], listeners: {}, dataset:{},
      classList: {toggle() {}, add() {}, remove() {}}, append(...values) {this.children.push(...values);},
      replaceChildren(...values) {this.children = values;},
      get lastChild() {return this.children.at(-1);},
      setAttribute() {}, addEventListener(event, fn) {this.listeners[event] = fn;},
      querySelector() {return element();}, focus() {}, close() {}, showModal() {}};
  }
  const document = {getElementById(id) {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);},
    createElement: element, createTextNode: value => ({textContent: value}),
    querySelectorAll: () => [], querySelector: () => null, body: element()};
  let saved;const stored=new Map();
  const context = vm.createContext({document, fetch, URL, URLSearchParams, Intl,
    crypto: {randomUUID}, AbortController, console,
    localStorage: {getItem: key => stored.get(key) || null, setItem: (key, value) => {stored.set(key,value);if(key==='shoptalk-session')saved=JSON.parse(value);}},
    setInterval() {}, setTimeout() {}, clearTimeout() {}});
  const source = fs.readFileSync('services/conversation/web/store.js', 'utf8').replace('safe(boot)();', '');
  vm.runInContext(source, context);
  vm.runInContext(`S = {namespace:'bench-ui', user_id:'ui-test', run_id:uid(), correlation_id:uid(),
    session_id:uid(), cart_id:uid(), cart:{version:1,lines:[]}};initialized=true;`, context);
  return {elements, run: code => vm.runInContext(code, context), saved: () => saved};
}

test('lost mutation response preserves the exact request identity through retry', async () => {
  const calls = [];
  const app = controller(async (path, options) => {
    calls.push({path, ...options});
    if (calls.length === 1) throw new Error('response lost');
    return {ok:true, json: async () => ({session_id:'accepted-session',cart_id:'accepted-cart'})};
  });
  await assert.rejects(app.run(`mutate('session','/v1/sessions',{})`), /response lost/);
  const pending = app.saved().pending;
  assert(pending.headers['Idempotency-Key']);
  await app.run('executePending()');
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].headers, calls[1].headers);
  assert.equal(calls[0].body, calls[1].body);
  assert.equal(app.saved().session_id, 'accepted-session');
  assert.equal(app.saved().pending, undefined);
});

test('checkout requires a current quote and explicit checked confirmation', async () => {
  const calls = [];
  const app = controller(async (path, options) => {
    calls.push({path, ...options});
    return {ok:true, json:async () => ({order_id:'synthetic-order',status:'CONFIRMED'})};
  });
  await app.run(`S.quote = {quote_id:uid(),cart_version:1,expires_at:new Date(Date.now()+60000).toISOString()};`);
  const button = app.elements.get('confirm-purchase');
  await button.listeners.click();
  assert.equal(calls.length, 0);
  app.elements.get('review-quote').checked = true;
  await button.listeners.click();
  const checkouts = calls.filter(c => c.path.endsWith('/checkout'));
  assert.equal(checkouts.length, 1);
  assert.equal(JSON.parse(checkouts[0].body).confirmed, true);
  assert.equal(app.saved().order_id, 'synthetic-order');
});

test('an expired quote remains blocked even when its checkbox is checked', async () => {
  const app = controller(async () => {throw new Error('must never checkout');});
  await app.run(`S.quote={quote_id:uid(),cart_version:1,expires_at:new Date(Date.now()-1000).toISOString()};`);
  app.elements.get('review-quote').checked = true;
  await app.elements.get('confirm-purchase').listeners.click();
  assert.equal(app.elements.get('confirm-purchase').disabled, true);
});

test('untrusted image schemes use the local placeholder', () => {
  const app = controller(async () => {});
  app.run(`image(document.getElementById('picture'), ['javascript:alert(1)'], 'Product');`);
  assert.equal(app.elements.get('picture').src, '/assets/placeholder.svg');
});

test('search prefers hybrid and keeps working when keyword search is available', () => {
  const app = controller(async () => {});
  app.run(`S.retrieval_preference='lexical'`);
  app.run(`configureRetrieval({search_modes:['lexical','hybrid_exact']})`);
  assert.equal(app.run('retrievalReady'), true);
  assert.equal(app.run('S.retrieval_preference'), undefined);
  app.run(`configureRetrieval({search_modes:['lexical']})`);
  assert.equal(app.run('retrievalReady'), true);
  assert.equal(app.run('retrievalMode'), 'lexical');
  assert.equal(app.elements.get('send-chat').disabled, false);
  app.run(`configureRetrieval({search_modes:[]})`);
  assert.equal(app.run('retrievalReady'), false);
});

test('the store removes the old mode preference and exposes no chat settings', () => {
  const app = controller(async () => {});
  app.run(`configureAssistant({conversation_available:true})`);
  app.run(`S.assistant_preference='fixed'`);
  app.run(`configureAssistant({conversation_available:true})`);
  assert.equal(app.run('S.assistant_preference'),undefined);
  assert.equal(app.elements.has('assistant-mode'),false);
  assert(!fs.readFileSync('services/conversation/web/index.html','utf8').includes('Chat settings'));
});

test('chat request uses the selected assistant independently of retrieval', async () => {
  const app = controller(async () => {});
  app.run(`globalThis.chatRequest=null; mutate=async(label,path,body)=>{globalThis.chatRequest=body};
    document.getElementById('assistant-mode').value='assist';`);
  await app.run(`sendChat('Find a gift')`);
  assert.equal(app.run('chatRequest.mode'), 'assist');
  assert.equal(app.run('chatRequest.retrieval_mode'), 'hybrid_exact');
  await app.run(`sendChat('shirts',undefined,'fixed')`);
  assert.equal(app.run('chatRequest.mode'), 'fixed');
  assert.equal(app.run('chatRequest.retrieval_mode'), 'hybrid_exact');
});

test('product results use shopper language without retrieval controls', () => {
  const app = controller(async () => {});
  app.run(`S.memory={retrieval_mode:'hybrid_exact'}; showChatProducts([]);`);
  assert.equal(app.elements.get('result-count').textContent, '0 matching products');
  assert.equal(app.elements.has('retrieval'), false);
});

test('a dependency error preserves displayed products and offers a fresh search retry', async () => {
  const calls = [];
  const app = controller(async (path, options) => {
    calls.push({path,...options});
    return {ok:true,json:async()=>path.endsWith('/shopping-turns') ?
      {outcome:'dependency_error',products:[]} : {conversation:{messages:[],intent:null,products:[]}}};
  });
  app.elements.get('products') || app.run("document.getElementById('products')");
  const previous={marker:'previous actual products'};
  app.elements.get('products').append(previous);
  await app.run("mutate('chat','/v1/sessions/test/shopping-turns',{text:'white shirt',mode:'fixed'})");
  assert.equal(app.elements.get('products').children[0],previous);
  assert.equal(app.elements.get('retry-chat').hidden,false);
  assert.equal(app.run('S.pending'),undefined);
  assert.equal(app.saved().failed_search.text,'white shirt');
  assert.match(app.elements.get('notice-text').textContent,/Search is temporarily unavailable/);
});

test('terminal order polling releases the quote control and analytics never submits checkout', async () => {
  const calls=[];
  const app=controller(async path=>{
    calls.push(path);
    return {ok:true,json:async()=>path.endsWith('/pipeline') ?
      {order_id:'test-order',order_version:6,status:'visible',generation:9} :
      {order_id:'test-order',order_version:6,status:'CONFIRMED'}};
  });
  app.run("S.cart.lines=[{sku:'TEST-SKU',quantity:1}]; S.order_id='test-order'; S.order={status:'PENDING'}; renderCart()");
  assert.equal(app.elements.get('request-quote').disabled,true);
  await app.run('pollOrder()');
  assert.equal(app.elements.get('request-quote').disabled,false);
  assert(calls.every(p=>p.startsWith('/v1/store/orders/')));
});

test('a capabilities outage shows search unavailable and does not switch algorithms', async () => {
  const app=controller(async()=>({ok:false,status:503,json:async()=>({error:{message:'unavailable'}})}));
  await app.run('loadRetrieval()');
  assert.equal(app.run('retrievalReady'), false);
  assert.equal(app.elements.get('send-chat').disabled,true);
  assert.match(app.elements.get('chat-status').textContent,/Search is unavailable/);
  assert.equal(app.run('S.pending'),undefined);
});

test('changing demo datasets preserves pending checkout identity without replaying it',()=>{
  const app=controller(async()=>{throw new Error('Dataset selection must not send a mutation');});
  app.run(`S.pending={label:'checkout',path:'/checkout',headers:{'Idempotency-Key':'original-key'},body:{confirmed:true}};connectDataset('bench-new');`);
  assert.equal(app.run('S.pending'),undefined);
  app.run(`S={namespace:'bench-new'};connectDataset('bench-ui');`);
  assert.equal(app.run('S.pending.headers["Idempotency-Key"]'),'original-key');
  assert.equal(app.run('S.pending.body.confirmed'),true);
});

test('Enter submits one ready message, Shift+Enter and composition do not submit',()=>{
  const app=controller(async()=>{});let submissions=0;
  app.elements.get('chat-form').requestSubmit=()=>submissions++;
  app.elements.get('chat-input').value='hello';app.run(`document.getElementById('send-chat').disabled=false`);
  const enter=app.elements.get('chat-input').listeners.keydown;
  const event={key:'Enter',shiftKey:false,isComposing:false,preventDefault(){}};
  enter(event);assert.equal(submissions,1);
  enter({...event,shiftKey:true});enter({...event,isComposing:true});assert.equal(submissions,1);
  app.elements.get('send-chat').disabled=true;enter(event);assert.equal(submissions,1);
});
