import {initializeApp} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import {getAuth, onAuthStateChanged, signInWithEmailAndPassword, signOut} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";

const config = await (await fetch("/__/firebase/init.json")).json();
const runtime = await (await fetch("/runtime-config.json", {cache: "no-store"})).json();
const auth = getAuth(initializeApp(config));
const api = window.DEAL_SNIPER_API ?? runtime.adminApiBase ?? runtime.apiBase ?? "";
let token = "";
let testedSourceKey = "";
const transientStatuses = new Set([429, 500, 502, 503, 504]);
const byId = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "—").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const number = (value) => new Intl.NumberFormat("en-AE").format(Number(value || 0));
const money = (value) => `${number(value)} AED`;

const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

async function call(path, options = {}, attempt = 0) {
  let response;
  try {
    response = await fetch(api + path, {...options, cache: "no-store", headers: {"Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options.headers}});
  } catch (error) {
    if (attempt < 2) { await wait(300 * (attempt + 1)); return call(path, options, attempt + 1); }
    throw new Error(`${path}: network or Gateway error`);
  }
  if (response.status === 401 && attempt === 0 && auth.currentUser) {
    token = await auth.currentUser.getIdToken(true);
    return call(path, options, attempt + 1);
  }
  if (transientStatuses.has(response.status) && attempt < 2) {
    await wait(300 * (attempt + 1));
    return call(path, options, attempt + 1);
  }
  if (!response.ok) {
    let message = `${path}: request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch { /* response was not JSON */ }
    throw new Error(message);
  }
  return response.json();
}

function statusPill(label, good = true) { return `<span class="status-pill ${good ? "status-good" : "status-bad"}">${safe(label)}</span>`; }
function metric(label, value, hint = "") { return `<article class="metric-card"><span>${safe(label)}</span><strong>${safe(value)}</strong><small>${safe(hint)}</small></article>`; }
function sourceState(run, enabled) {
  if (!enabled) return {label: "Paused", good: false};
  if (!run || Object.keys(run).length === 0) return {label: "Not run", good: false};
  if (run.success === true && !run.error) return {label: "Healthy", good: true};
  return {label: "Attention", good: false};
}
function shortName(value) { const text = String(value || ""); return text.split("/").pop() || text || "Unknown"; }
function keyValues(values) { return Object.entries(values || {}).map(([key, value]) => `<div><span>${safe(key.replaceAll("_", " "))}</span><strong>${safe(typeof value === "object" ? JSON.stringify(value) : value)}</strong></div>`).join(""); }

function renderSources(data) {
  const entries = Object.entries(data.source_switches || {});
  const dynamicSources = new Set(data.dynamic_sources || []);
  let healthy = 0;
  byId("sources").innerHTML = entries.map(([name, enabled]) => {
    const run = data.sources?.[name] || {};
    const state = sourceState(run, enabled);
    if (state.good) healthy += 1;
    const stats = run.error ? `<span class="source-error" title="${safe(run.error)}">${safe(String(run.error).slice(0, 120))}</span>` : `<span>${number(run.fetched)} fetched</span><span>${number(run.new)} new</span><span>${number(run.changed)} changed</span><span>${safe(run.duration_seconds || "—")} sec</span>`;
    const remove = dynamicSources.has(name) ? `<button class="danger-button remove-source" data-source="${safe(name)}">Remove</button>` : "";
    return `<article class="data-row"><div class="data-primary"><div><strong>${safe(name)}</strong>${dynamicSources.has(name) ? statusPill("Custom feed", true) : ""}${statusPill(state.label, state.good)}</div><div class="row-meta">${stats}</div></div><div class="row-actions"><button class="secondary run-source" data-source="${safe(name)}" ${enabled ? "" : "disabled"}>Run now</button><button class="toggle-source ${enabled ? "danger-button" : ""}" data-source="${safe(name)}" data-enabled="${enabled}">${enabled ? "Pause" : "Enable"}</button>${remove}</div></article>`;
  }).join("") || '<div class="empty-state">No source adapters installed.</div>';
  byId("source-brief").innerHTML = entries.map(([name, enabled]) => { const state = sourceState(data.sources?.[name], enabled); return `<div class="brief-row"><strong>${safe(name)}</strong>${statusPill(state.label, state.good)}</div>`; }).join("");
  byId("source-summary").className = `status-pill ${healthy === entries.length && entries.length ? "status-good" : "status-bad"}`;
  byId("source-summary").textContent = `${healthy}/${entries.length} healthy`;
  document.querySelectorAll(".toggle-source").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try { await call(`/admin/sources/${button.dataset.source}`, {method: "POST", body: JSON.stringify({enabled: button.dataset.enabled !== "true"})}); await refresh(); }
    catch (error) { showError(error); button.disabled = false; }
  }));
  document.querySelectorAll(".run-source").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true; button.textContent = "Starting…";
    try { await call(`/admin/sources/${button.dataset.source}/run`, {method: "POST"}); button.textContent = "Started"; window.setTimeout(refresh, 5000); }
    catch (error) { showError(error); button.disabled = false; button.textContent = "Run now"; }
  }));
  document.querySelectorAll(".remove-source").forEach((button) => button.addEventListener("click", async () => {
    if (!window.confirm(`Remove ${button.dataset.source}? Collected history will be kept.`)) return;
    button.disabled = true;
    try { await call(`/admin/sources/${button.dataset.source}/remove`, {method: "POST"}); await refresh(); }
    catch (error) { showError(error); button.disabled = false; }
  }));
}

function sourcePayload() {
  const name = byId("source-name").value.trim().toLowerCase();
  const url = byId("source-url").value.trim();
  if (!/^[a-z][a-z0-9_-]{2,39}$/.test(name)) throw new Error("Use 3–40 lowercase letters, numbers, _ or - for the source name.");
  if (!url.startsWith("https://")) throw new Error("Enter a public HTTPS JSON feed URL.");
  return {name, url, kind: "json_feed"};
}

async function testNewSource() {
  const result = byId("source-test-result");
  byId("test-source").disabled = true; byId("add-source").disabled = true;
  result.className = "muted"; result.textContent = "Testing the feed and fixed prices…";
  try {
    const payload = sourcePayload();
    const response = await call("/admin/source-test", {method: "POST", body: JSON.stringify(payload)});
    testedSourceKey = JSON.stringify(payload); byId("add-source").disabled = false;
    result.className = "test-good";
    result.textContent = `${number(response.count)} valid vehicles found. Sample: ${response.sample.title} — ${money(response.sample.price_aed)}.`;
  } catch (error) {
    testedSourceKey = ""; result.className = "test-bad";
    result.textContent = error instanceof Error ? error.message : String(error);
  } finally { byId("test-source").disabled = false; }
}

async function addNewSource() {
  try {
    const payload = sourcePayload();
    if (JSON.stringify(payload) !== testedSourceKey) throw new Error("Test this exact name and URL first.");
    byId("add-source").disabled = true;
    await call("/admin/sources", {method: "POST", body: JSON.stringify(payload)});
    byId("source-name").value = ""; byId("source-url").value = ""; testedSourceKey = "";
    byId("source-test-result").className = "test-good";
    byId("source-test-result").textContent = "Source added paused. Review it below, then click Enable.";
    await refresh();
  } catch (error) { byId("source-test-result").className = "test-bad"; byId("source-test-result").textContent = error instanceof Error ? error.message : String(error); }
}

function renderCloud(cloud = {}) {
  const groups = [["Scheduler", cloud.scheduler], ["Task queues", cloud.queues], ["Cloud Run", cloud.services]];
  byId("cloud").innerHTML = groups.map(([label, items]) => {
    const values = Array.isArray(items) ? items : [];
    const unavailable = values.some((item) => item.state === "UNAVAILABLE");
    const body = unavailable ? '<div class="empty-state error-state">Status unavailable. Check runtime viewer permissions.</div>' : values.map((item) => `<div class="brief-row"><strong>${safe(shortName(item.name))}</strong>${statusPill(item.state || (item.latestReadyRevision ? "Ready" : "Active"), true)}</div>`).join("") || '<div class="empty-state">No resources found.</div>';
    return `<section class="admin-card"><div class="card-heading"><div><p class="eyebrow">GOOGLE CLOUD</p><h2>${safe(label)}</h2></div>${statusPill(unavailable ? "Unavailable" : "Connected", !unavailable)}</div>${body}</section>`;
  }).join("");
}

function render(data, pulse, preview, exceptions) {
  const sourceEntries = Object.entries(data.source_switches || {});
  const sourceHealthy = sourceEntries.filter(([name, enabled]) => sourceState(data.sources?.[name], enabled).good).length;
  byId("overview").innerHTML = metric("Listings stored", number(data.snapshot_count), "immutable snapshots") + metric("Sources healthy", `${sourceHealthy}/${sourceEntries.length}`, "installed adapters") + metric("Delivery", data.delivery_enabled ? "Running" : "Paused", "Telegram publishing") + metric("Schema", `v${data.schema_version}`, "production data");
  renderSources(data); renderCloud(data.cloud);
  byId("operations").innerHTML = keyValues(data.operations);
  byId("pulse").textContent = pulse.text || pulse.summary || "No market update is currently available.";
  byId("free").textContent = preview.free || "No current deal."; byId("pro").textContent = preview.pro || "No current deal.";
  byId("queue-brief").innerHTML = keyValues({delivery: data.delivery_enabled ? "running" : "paused", exceptions: exceptions.length, whatsapp: data.whatsapp_status});
  byId("subscription-brief").innerHTML = keyValues({price: money(data.subscription?.price_aed), active: data.subscription?.active || 0, total: data.subscription?.total || 0});
  byId("business-metrics").innerHTML = metric("Monthly price", money(data.subscription?.price_aed), "per Pro subscriber") + metric("Active Pro", number(data.subscription?.active), "Telegram subscriptions") + metric("Referrals", number(data.referrals?.total), "recorded invitations") + metric("WhatsApp", data.whatsapp_status, "channel relay");
  byId("financial").innerHTML = keyValues({...data.financial_config, pro_price_aed: data.subscription?.price_aed});
  byId("unknown").innerHTML = exceptions.map((item) => `<article class="data-row"><div class="data-primary"><strong>${safe(item.delivery_id)}</strong><span class="source-error">${safe(item.last_error || "Ambiguous delivery result")}</span></div><div class="row-actions">${["mark_sent", "mark_failed", "retry_once"].map((action) => `<button class="secondary reconcile" data-id="${safe(item.delivery_id)}" data-action="${action}">${safe(action.replaceAll("_", " "))}</button>`).join("")}</div></article>`).join("") || '<div class="empty-state">No delivery exceptions. Everything is reconciled.</div>';
  document.querySelectorAll(".reconcile").forEach((button) => button.addEventListener("click", () => reconcile(button.dataset.id, button.dataset.action)));
}

function showError(caught) { byId("error").hidden = false; byId("error").textContent = caught instanceof Error ? caught.message : String(caught); }
async function reconcile(deliveryId, action) { try { await call(`/admin/outbox/${encodeURIComponent(deliveryId)}/reconcile`, {method: "POST", body: JSON.stringify({action})}); await refresh(); } catch (error) { showError(error); } }
async function refresh() {
  byId("error").hidden = true; byId("refresh").disabled = true;
  try {
    const requests = [call("/admin/overview"), call("/content/market-pulse"), call("/admin/preview"), call("/admin/outbox?state=unknown"), call("/admin/outbox?state=failed")];
    const [overviewResult, pulseResult, previewResult, unknownResult, failedResult] = await Promise.allSettled(requests);
    if (overviewResult.status === "rejected") throw overviewResult.reason;
    const pulse = pulseResult.status === "fulfilled" ? pulseResult.value : {};
    const preview = previewResult.status === "fulfilled" ? previewResult.value : {};
    const unknown = unknownResult.status === "fulfilled" ? unknownResult.value : {items: []};
    const failed = failedResult.status === "fulfilled" ? failedResult.value : {items: []};
    render(overviewResult.value, pulse, preview, [...(unknown.items || []), ...(failed.items || [])]);
    const partialErrors = [pulseResult, previewResult, unknownResult, failedResult].filter((result) => result.status === "rejected");
    if (partialErrors.length) showError(new Error(`${partialErrors.length} section(s) are temporarily unavailable. Refresh will retry them.`));
    byId("updated").textContent = `Updated ${new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}`;
  } catch (error) { showError(error); } finally { byId("refresh").disabled = false; }
}

document.querySelectorAll(".admin-nav button").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".admin-nav button").forEach((item) => item.classList.toggle("active", item === button));
  document.querySelectorAll(".admin-view").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === button.dataset.view));
  byId("page-title").textContent = button.textContent;
}));
byId("login").addEventListener("click", async () => {
  byId("error").hidden = true;
  const email = byId("login-email").value.trim();
  const password = byId("login-password").value;
  if (!email) { showError(new Error("Enter the administrator email address.")); return; }
  if (!password) { showError(new Error("Enter the administrator password.")); return; }
  byId("login").disabled = true;
  try {
    await signInWithEmailAndPassword(auth, email, password);
    byId("login-password").value = "";
  } catch (error) { showError(error); } finally { byId("login").disabled = false; }
});
byId("logout").addEventListener("click", () => signOut(auth)); byId("refresh").addEventListener("click", refresh);
byId("test-source").addEventListener("click", testNewSource); byId("add-source").addEventListener("click", addNewSource);
[byId("source-name"), byId("source-url")].forEach((input) => input.addEventListener("input", () => { testedSourceKey = ""; byId("add-source").disabled = true; }));
onAuthStateChanged(auth, async (user) => {
  if (!user) {
    token = ""; byId("identity").textContent = "Not signed in"; byId("login").hidden = false; byId("login-email").hidden = false; byId("login-password").hidden = false; byId("logout").hidden = true; byId("refresh").disabled = true; byId("auth-notice").hidden = false;
    return;
  }
  try {
    token = await user.getIdToken(); byId("identity").textContent = user.email || "Administrator"; byId("login").hidden = true; byId("login-email").hidden = true; byId("login-password").hidden = true; byId("logout").hidden = false; byId("auth-notice").hidden = true; byId("refresh").disabled = false; await refresh();
  } catch (error) {
    token = ""; byId("refresh").disabled = true;
    showError(new Error("Firebase session could not be established. Reload the page and sign in again."));
  }
});
