// Browser-independent controller checks; these do not claim visual browser coverage.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const {randomUUID} = require('node:crypto');

function controller(fetch) {
  const elements = new Map();
  function element() {
    return {checked: false, disabled: false, hidden: false, children: [], listeners: {},
      classList: {toggle() {}}, append(...values) {this.children.push(...values);},
      replaceChildren(...values) {this.children = values;},
      get lastChild() {return this.children.at(-1);},
      setAttribute() {}, addEventListener(event, fn) {this.listeners[event] = fn;},
      querySelector() {return element();}, focus() {}, close() {}, showModal() {}};
  }
  const document = {getElementById(id) {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);},
    createElement: element, createTextNode: value => ({textContent: value}),
    querySelectorAll: () => [], body: element()};
  let saved;
  const context = vm.createContext({document, fetch, URL, URLSearchParams, Intl,
    crypto: {randomUUID}, AbortController, console,
    localStorage: {getItem: () => null, setItem: (_, value) => {saved = JSON.parse(value);}},
    setInterval() {}, setTimeout() {}, clearTimeout() {}});
  const source = fs.readFileSync('services/conversation/web/store.js', 'utf8').replace('safe(boot)();', '');
  vm.runInContext(source, context);
  vm.runInContext(`S = {namespace:'bench-ui', user_id:'ui-test', run_id:uid(), correlation_id:uid(),
    session_id:uid(), cart_id:uid(), cart:{version:1,lines:[]}};`, context);
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
