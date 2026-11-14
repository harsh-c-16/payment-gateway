"use strict";

const $ = (id) => document.getElementById(id);
const uid = () => crypto.randomUUID();
const money = (minor, currency = "INR") => new Intl.NumberFormat("en-IN", {style: "currency", currency}).format(minor / 100);
const text = (tag, value, className = "") => { const n = document.createElement(tag); n.textContent = value; n.className = className; return n; };
const cache = new Map();
let S;
try { S = JSON.parse(localStorage.getItem("shoptalk-session")) || {}; } catch { S = {}; }
const RETRIEVAL_MODE = "hybrid_exact";
let retrievalReady = false;
let busy = false, offset = 0, pageTotal = 0, chatView = false, orderTimer, pipelineTimer;
const save = () => localStorage.setItem("shoptalk-session", JSON.stringify(S));
const contextHeaders = (requestId = uid()) => ({
  "Content-Type": "application/json", "Accept": "application/json", "X-Namespace": S.namespace,
  "X-User-ID": S.user_id, "X-Run-ID": S.run_id, "X-Correlation-ID": S.correlation_id,
  "X-Request-ID": requestId, ...(S.session_id ? {"X-Session-ID": S.session_id} : {}),
});

class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
async function request(path, {method = "GET", body, headers = contextHeaders()} = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), path.endsWith('/shopping-turns') ? 30000 : 12000);
  try {
    const response = await fetch(path, {method, body: body === undefined ? undefined : JSON.stringify(body), headers,
      signal: controller.signal, cache: "no-store", credentials: "omit"});
    let data;
    try { data = await response.json(); }
    catch { throw new ApiError("The service returned an unreadable response. Please retry.", response.status); }
    if (!response.ok) throw new ApiError(data.error?.message || `Service returned ${response.status}.`, response.status);
    return data;
  } finally { clearTimeout(timer); }
}
function notice(message, error = false) {
  $("notice").hidden = !message;
  $("notice-text").textContent = message;
  $("notice").classList.toggle("error", error);
  $("retry-pending").hidden = !S.pending;
  $("retry-load").hidden = !error || !!S.pending;
  $("retry-chat").hidden = !S.failed_search || !!S.pending;
}
function setBusy(value) {
  busy = value;
  document.body.classList.toggle("busy", value);
  $("send-chat").disabled = value || !retrievalReady;
  $("more-options").disabled = value || !S.memory?.intent || !retrievalReady;
  $("new-search").disabled = value;
  document.querySelectorAll("[data-prompt]").forEach(button => { button.disabled = value || !retrievalReady; });
  $("chat-status").hidden = !value && retrievalReady;
  $("chat-status").classList.toggle("error", !value && !retrievalReady);
  $("chat-status").textContent = value ? "Working on it…" : retrievalReady ? "" :
    "Product search is temporarily unavailable. You can still browse the collection. Please try again shortly.";
  $("request-quote").disabled = value || !S.cart?.lines.length;
  refreshConfirmation();
}
const safe = (action) => async (event) => {
  event?.preventDefault();
  try { await action(event); } catch (error) {
    const message = S.pending ? "We couldn't confirm the result. Choose Retry saved request to safely check again. " + error.message : error.message;
    notice(message, true);
    $("chat-status").textContent = message;
    $("chat-status").hidden = false;
    $("chat-status").classList.add("error");
  }
};

async function applyMutation(operation, data) {
  if (operation.label === "session") {
    S.session_id = data.session_id; S.cart_id = data.cart_id;
  } else if (operation.label === "cart") {
    S.cart = data; S.quote = null;
  } else if (operation.label === "quote") {
    S.quote = data; $("review-quote").checked = false;
  } else if (operation.label === "checkout") {
    S.order_id = data.order_id; S.order = data; S.quote = null;
  }
  save();
}
async function executePending() {
  if (!S.pending) return;
  const operation = S.pending;
  setBusy(true);
  try {
    const data = await request(operation.path, operation);
    // Persist the accepted resource before clearing its retry identity.
    await applyMutation(operation, data);
    delete S.pending; save();
    notice("");
    if (operation.label === "chat") {
      await restoreConversation();
      if (data.outcome === "dependency_error") {
        S.failed_search = operation.body; save();
        notice((data.response_text || "Search is temporarily unavailable.") + " Your previous results and preferences are kept. Retry this search.", true);
      } else {
        delete S.failed_search; save();
        $("chat-input").value = "";
        if (data.outcome === "success") showChatProducts(data.products);
      }
    }
    if (operation.label === "checkout") pollOrder();
    renderCart();
    return data;
  } catch (error) {
    if (error.status >= 400 && error.status < 500 && ![408, 429].includes(error.status)) {
      delete S.pending; save();
      if (error.status === 409) { S.quote = null; await loadCart(); }
    }
    throw error;
  } finally { setBusy(false); renderCart(); }
}
async function mutate(label, path, body, method = "POST") {
  if (busy) throw new Error("Please wait for the current request to finish.");
  if (S.pending) throw new Error("Finish retrying the saved request before starting a different action.");
  const requestId = uid();
  if (label === "chat") body = {...body, request_id: requestId};
  S.pending = {label, path, body, method, headers: {...contextHeaders(requestId), "Idempotency-Key": uid()}};
  save();
  return executePending();
}

function image(element, urls, alt) {
  let selected = "/assets/placeholder.svg";
  for (const raw of urls || []) {
    try { const u = new URL(raw); if (["https:", "http:"].includes(u.protocol) && !u.username && !u.password) { selected = u.href; break; } } catch { /* Unusable source link: use a local placeholder. */ }
  }
  element.alt = alt; element.referrerPolicy = "no-referrer";
  const fallback = () => { clearTimeout(timer); element.onerror = null; element.src = "/assets/placeholder.svg"; };
  const timer = setTimeout(() => { if (!element.complete || !element.naturalWidth) fallback(); }, 5000);
  element.onload = () => clearTimeout(timer);
  element.onerror = fallback;
  element.src = selected;
}
function renderProducts(products) {
  $("products").replaceChildren(); $("empty").hidden = products.length > 0;
  for (const p of products) {
    cache.set(p.sku, p);
    const card = $("product-card").content.cloneNode(true);
    image(card.querySelector("img"), p.image_urls, p.title);
    card.querySelector(".product-category").textContent = p.category?.replaceAll("_", " ") || "Our catalogue";
    card.querySelector(".product-title").textContent = p.title;
    card.querySelector(".product-price").textContent = money(p.price_minor, p.currency);
    card.querySelector(".product-stock").textContent = p.stock_available > 0 ? "Available · rechecked at checkout" : "Currently unavailable";
    for (const button of card.querySelectorAll("button")) {
      if (button.dataset.action === "add") {
        button.disabled = !p.stock_available;
        button.setAttribute("aria-label", `Add ${p.title} to cart`);
      }
      button.addEventListener("click", safe(() => button.dataset.action === "add" ? addToCart(p.sku) : showProduct(p.sku)));
    }
    $("products").append(card);
  }
}
function showChatProducts(products) {
  chatView = true;
  S.view = "chat"; save();
  $("results-title").textContent = "Picked for your preferences";
  $("result-count").textContent = `${products.length} matching ${products.length === 1 ? "product" : "products"}`;
  $("browse-reset").hidden = false; $("pagination").hidden = true;
  renderProducts(products);
}
async function browse(reset = true) {
  if (reset) offset = 0;
  chatView = false;
  S.view = "browse"; save();
  const params = new URLSearchParams({q: $("search").value.trim(), sort: $("sort").value, offset, limit: 12});
  if ($("category").value) params.set("category", $("category").value);
  if ($("budget").value !== "") {
    const value = Number($("budget").value);
    if (!Number.isFinite(value) || value < 0) throw new Error("Enter a valid maximum price in rupees.");
    params.set("max_price_minor", Math.round(value * 100));
  }
  $("result-count").textContent = "Finding products…";
  const page = await request("/v1/store/products?" + params);
  pageTotal = page.total;
  $("results-title").textContent = $("search").value.trim() ? `Results for “${$("search").value.trim()}”` : "Discover something good";
  $("result-count").textContent = $("search").value.trim() ?
    `${page.total} top matches${$("sort").value !== "relevance" ? " · sorted by price" : ""}` :
    `${page.total.toLocaleString("en-IN")} products`;
  $("browse-reset").hidden = true;
  renderProducts(page.items);
  $("pagination").hidden = page.total <= 12;
  $("page-info").textContent = `Page ${Math.floor(offset / 12) + 1} of ${Math.max(1, Math.ceil(page.total / 12))}`;
  $("previous").disabled = offset === 0; $("next").disabled = offset + 12 >= pageTotal;
}
async function restoreConversation() {
  const snapshot = await request(`/v1/sessions/${S.session_id}`);
  S.memory = snapshot.conversation; save();
  $("messages").replaceChildren();
  for (const message of S.memory.messages || []) {
    const block = text("div", "", "message " + (message.role === "user" ? "user" : "assistant"));
    block.append(text("span", message.role === "user" ? "You" : "ShopTalk", "message-label"), document.createTextNode(message.text));
    $("messages").append(block);
  }
  const scroll = document.querySelector(".chat-scroll");
  if (scroll) scroll.scrollTop = scroll.scrollHeight;
  const intent = S.memory.intent;
  $("preferences-panel").hidden = !intent;
  if (intent) {
    const values = [intent.query_text, ...["category", "colour", "material", "brand", "size"].filter(k => intent[k]).map(k => `${k}: ${intent[k]}`)];
    if (intent.max_price_minor !== null && intent.max_price_minor !== undefined) values.push(`maximum ${money(intent.max_price_minor)}`);
    $("preferences").textContent = "Remembered preferences: " + values.filter(Boolean).join(" · ");
  }
  $("more-options").disabled = busy || !intent || !retrievalReady;
  for (const p of S.memory.products || []) cache.set(p.sku, p);
}
async function sendChat(value, selectedSku, assistantMode = $("assistant-mode").value || "fixed") {
  if (!value.trim()) return;
  await mutate("chat", `/v1/sessions/${S.session_id}/shopping-turns`, {
    text: value.trim(), mode: assistantMode, retrieval_mode: RETRIEVAL_MODE,
    ...(selectedSku ? {selected_sku: selectedSku} : {}),
  });
}
async function showProduct(sku) {
  const response = await request("/v1/store/products/" + encodeURIComponent(sku));
  const p = response.product, stock = response.stock;
  cache.set(sku, {...p, stock_available: stock?.available || 0});
  const detail = $("product-detail"); detail.replaceChildren();
  const picture = document.createElement("img"); image(picture, p.image_urls, p.title);
  const heading = text("h2", p.title); heading.id = "product-title";
  detail.append(picture, heading, text("p", p.price_minor === null ? "Not currently sellable" : money(p.price_minor), "product-price"));
  const facts = document.createElement("dl");
  for (const [label, value] of [["Brand", p.brand], ["Category", p.category], ["Colour", p.colour], ["Material", p.material], ["Size", p.size], ["Available", stock?.available], ["SKU", p.sku]]) {
    facts.append(text("dt", label), text("dd", value === null || value === undefined ? "Not recorded" : String(value)));
  }
  detail.append(facts, text("p", p.description || "No description was provided for this listing.", "muted"));
  const controls = text("div", "", "detail-actions");
  const add = text("button", "Add to cart", "primary"); add.type = "button";
  add.disabled = !p.active || p.price_minor === null || !stock?.available;
  add.addEventListener("click", safe(() => addToCart(sku)));
  controls.append(add); detail.append(controls);
  if (!$("product-dialog").open) $("product-dialog").showModal();
}
async function loadCart() {
  S.cart = await request(`/v1/carts/${S.cart_id}`);
  if (S.quote && S.quote.cart_version !== S.cart.version) S.quote = null;
  save(); renderCart();
}
async function addToCart(sku) {
  await loadCart();
  const current = S.cart.lines.find(line => line.sku === sku)?.quantity || 0;
  if (current >= 10) throw new Error("The maximum quantity per product is 10.");
  await updateQuantity(sku, current + 1);
  notice("Added to your cart. Open Cart when you're ready to review your order.");
}
async function updateQuantity(sku, quantity) {
  await mutate("cart", `/v1/carts/${S.cart_id}/items/${encodeURIComponent(sku)}`, {quantity, expected_cart_version: S.cart.version}, "PUT");
}
function renderCart() {
  const cart = S.cart;
  $("cart-count").textContent = cart ? cart.lines.reduce((n, l) => n + l.quantity, 0) : 0;
  $("cart-lines").replaceChildren();
  if (!cart?.lines.length) $("cart-lines").append(text("p", "Your cart is ready for your first find.", "muted"));
  for (const line of cart?.lines || []) {
    const row = text("div", "", "cart-line");
    const name = text("div", cache.get(line.sku)?.title || line.sku, "cart-line-name");
    const controls = text("div", "", "quantity-controls");
    for (const delta of [-1, 1]) {
      const b = text("button", delta === -1 ? "−" : "+"); b.type = "button";
      b.setAttribute("aria-label", `${delta === -1 ? "Decrease" : "Increase"} quantity of ${cache.get(line.sku)?.title || line.sku}`);
      b.disabled = busy || line.quantity + delta > 10;
      b.addEventListener("click", safe(() => updateQuantity(line.sku, line.quantity + delta)));
      if (delta === 1) controls.append(text("span", String(line.quantity)));
      controls.append(b);
    }
    row.append(name, controls); $("cart-lines").append(row);
  }
  $("quote").replaceChildren();
  if (S.quote) {
    const box = text("div", "", "quote-box");
    box.append(text("h3", "Order summary"));
    for (const line of S.quote.lines) {
      const row = text("div", "", "quote-line");
      row.append(text("span", `${line.quantity} × ${cache.get(line.sku)?.title || line.sku}`), text("span", money(line.line_total_minor, S.quote.currency)));
      box.append(row);
    }
    box.append(text("p", `Total ${money(S.quote.total_amount_minor, S.quote.currency)}`, "quote-total"), text("p", "", "quote-meta"));
    box.lastChild.id = "quote-expiry"; $("quote").append(box);
  }
  $("request-quote").disabled = busy || !cart?.lines.length || unresolvedOrder();
  $("request-quote").textContent = S.quote ? "Update order summary" : "Review order";
  $("request-quote").className = S.quote ? "secondary" : "primary";
  renderOrder(); refreshConfirmation();
}
function unresolvedOrder() { return S.order_id && !["CONFIRMED", "CANCELLED"].includes(S.order?.status); }
function refreshConfirmation() {
  const valid = !!S.quote && Number.isFinite(Date.parse(S.quote.expires_at)) && Date.parse(S.quote.expires_at) > Date.now() && S.quote.cart_version === S.cart?.version;
  $("review-label").hidden = !S.quote; $("confirm-purchase").hidden = !S.quote;
  $("confirm-purchase").disabled = !valid || !$("review-quote").checked || busy || !!S.pending;
  if ($("quote-expiry") && S.quote) $("quote-expiry").textContent = valid ? `These prices are held until ${new Date(S.quote.expires_at).toLocaleTimeString()}. Place your order before then, or update the summary.` : "Your summary needs updating. Select Update order summary to check the latest prices.";
}
function renderOrder() {
  const expanded = $("order").querySelector("details")?.open;
  $("order").replaceChildren();
  if (!S.order_id) return;
  const box = text("div", "", "order-box"), status = S.order?.status || "PENDING";
  const titles = {CONFIRMED:"Order confirmed", CANCELLED:"Order cancelled", MANUAL_REVIEW:"Order needs attention"};
  box.append(text("h3", titles[status] || "Placing your order"), text("p", `Order ${S.order_id}`, "quote-meta"));
  const explanation = {CONFIRMED: "Your demo order has been placed. You're all set!", CANCELLED: "We couldn't complete this order. You can review your cart and try again.", MANUAL_REVIEW: "We're checking a problem with this order. Please keep this order number and avoid placing it again."};
  box.append(text("p", explanation[status] || "We're checking stock and processing your demo order. This page updates automatically."));
  if (S.order?.total_amount_minor !== undefined) box.append(text("p", `Order total ${money(S.order.total_amount_minor, S.order.currency)}`));
  const details = document.createElement("details");
  details.open = !!expanded;
  details.append(text("summary", "Order processing and analytics"));
  const steps = text("dl", "", "order-journey");
  for (const [label, value] of [["Stock reservation", S.order?.reservation_id ? "Reservation recorded" : "Waiting"],
    ["Simulated payment", S.order?.payment_id ? "Payment attempt recorded" : "Waiting"],
    ["Order status", status.replaceAll("_", " ")]]) steps.append(text("dt", label), text("dd", value));
  const pipeline = S.pipeline?.order_id === S.order_id && S.pipeline.order_version === S.order?.order_version ? S.pipeline : null;
  const publication = pipeline?.status === "visible" ? `Published in Gold · generation ${pipeline.generation}` :
    pipeline?.status === "unavailable" ? "Analytics unavailable · retrying; your order is unchanged" : "Waiting for the analytics pipeline";
  steps.append(text("dt", "Analytics record"), text("dd", publication));
  details.append(steps); box.append(details);
  box.dataset.pipelineStatus = pipeline?.status || "pending";
  const b = text("button", "Refresh order status", "secondary"); b.type = "button";
  b.addEventListener("click", safe(() => pollOrder())); box.append(b); $("order").append(box);
}
async function pollOrder(started = Date.now()) {
  clearTimeout(orderTimer);
  try {
    S.order = await request("/v1/store/orders/" + S.order_id); save(); renderCart();
    if (["CONFIRMED", "CANCELLED", "MANUAL_REVIEW"].includes(S.order.status)) pollPipeline();
    if (!["CONFIRMED", "CANCELLED", "MANUAL_REVIEW"].includes(S.order.status) && Date.now() - started < 120000) {
      orderTimer = setTimeout(() => pollOrder(started), 1500);
    }
  } catch (error) { notice("Order status is unavailable. The purchase has not been resubmitted. " + error.message, true); }
}
async function pollPipeline(started = Date.now()) {
  clearTimeout(pipelineTimer);
  const orderId = S.order_id;
  try {
    const value = await request(`/v1/store/orders/${orderId}/pipeline`);
    if (S.order_id !== orderId) return;
    S.pipeline = value; save(); renderOrder();
    if (value.status === "visible" && value.order_version === S.order?.order_version) return;
  } catch { /* Analytics availability never changes or resubmits a purchase. */ }
  if (Date.now() - started < 120000 && S.order_id === orderId) pipelineTimer = setTimeout(() => pollPipeline(started), 2500);
}
async function boot() {
  const config = await request("/v1/store/bootstrap", {headers: {"Accept": "application/json"}});
  configureAssistant(config);
  if (S.namespace && S.namespace !== config.namespace) throw new Error("This saved session belongs to another namespace. Keep its saved state and open this deployment in a separate browser profile.");
  S.namespace = config.namespace; S.user_id ||= "shopper-" + uid(); S.run_id ||= uid(); S.correlation_id ||= uid(); save();
  if (!S.session_id && !S.pending) await mutate("session", "/v1/sessions", {});
  if (S.pending) await executePending();
  await loadCart(); await restoreConversation();
  const facets = await request("/v1/store/facets");
  $("category").replaceChildren(new Option("All categories", "")); $("category-chips").replaceChildren();
  for (const root of facets.roots) $("category").append(new Option(root.label, root.id));
  for (const root of facets.roots.slice(0, 6)) {
    const chip = text("button", root.label); chip.type = "button";
    chip.addEventListener("click", safe(async () => { $("category").value = root.id; $("search").value = ""; await browse(); }));
    $("category-chips").append(chip);
  }
  await loadRetrieval();
  if (S.view === "chat" && S.memory.intent) showChatProducts(S.memory.products || []);
  else await browse();
  if (S.order_id) pollOrder();
}
function configureRetrieval(capabilities) {
  retrievalReady = capabilities.search_modes.includes(RETRIEVAL_MODE);
  delete S.retrieval_preference; save();
  setBusy(busy);
  if (!retrievalReady) {
    $("chat-status").hidden = false;
    $("chat-status").textContent = "Product search is temporarily unavailable. You can still browse the collection. Please try again shortly.";
    $("chat-status").classList.add("error");
  }
}
function configureAssistant(config) {
  $("assistant-mode").querySelector('[value="assist"]').disabled = !config.conversation_available;
  $("assistant-mode").value = config.conversation_available && S.assistant_preference !== "fixed" ? "assist" : "fixed";
  $("assistant-note").textContent = config.conversation_available ?
    "AI chat remembers your preferences during this visit." :
    "AI chat is unavailable. Basic chat can still help you find products.";
}
$("assistant-mode").addEventListener("change", () => { S.assistant_preference = $("assistant-mode").value; save(); });
async function loadRetrieval() {
  try {
    const capabilities = await request("/v1/store/capabilities");
    configureRetrieval(capabilities);
  } catch {
    configureRetrieval({search_modes:[]});
  }
}

$("search-form").addEventListener("submit", safe(() => browse()));
$("filters").addEventListener("submit", safe(() => browse()));
$("browse-reset").addEventListener("click", safe(() => browse()));
$("previous").addEventListener("click", safe(async () => { offset = Math.max(0, offset - 12); await browse(false); }));
$("next").addEventListener("click", safe(async () => { if (offset + 12 < pageTotal) { offset += 12; await browse(false); } }));
$("chat-form").addEventListener("submit", safe(() => sendChat($("chat-input").value)));
$("chat-input").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("chat-form").requestSubmit(); } });
document.querySelectorAll("[data-prompt]").forEach(b => b.addEventListener("click", safe(() => sendChat(b.dataset.prompt))));
$("more-options").addEventListener("click", safe(() => sendChat("Show more options")));
$("new-search").addEventListener("click", () => { $("chat-input").value = "New search: "; $("chat-input").focus(); });
$("cart-open").addEventListener("click", safe(async () => { await loadCart(); $("cart-dialog").showModal(); }));
document.querySelectorAll("[data-close]").forEach(b => b.addEventListener("click", () => $(b.dataset.close).close()));
$("request-quote").addEventListener("click", safe(() => mutate("quote", `/v1/carts/${S.cart_id}/quote`, {expected_cart_version: S.cart.version})));
$("review-quote").addEventListener("change", refreshConfirmation);
$("confirm-purchase").addEventListener("click", safe(async () => {
  refreshConfirmation();
  if ($("confirm-purchase").disabled) return;
  const quote = S.quote;
  await mutate("checkout", `/v1/carts/${S.cart_id}/checkout`, {
    quote_id: quote.quote_id, expected_cart_version: quote.cart_version, confirmed: true, confirmation_id: uid(),
  });
}));
$("retry-pending").addEventListener("click", safe(executePending));
$("retry-load").addEventListener("click", safe(() => boot()));
$("retry-chat").addEventListener("click", safe(async () => {
  if (S.failed_search) await sendChat(S.failed_search.text, S.failed_search.selected_sku, S.failed_search.mode);
}));
setInterval(refreshConfirmation, 1000);
safe(boot)();
