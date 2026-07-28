import {initializeApp} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import {getAuth, getRedirectResult, GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signInWithRedirect, signOut} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";

const config = await (await fetch("/__/firebase/init.json")).json();
const runtime = await (await fetch("/runtime-config.json", {cache: "no-store"})).json();
const auth = getAuth(initializeApp(config));
const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({prompt: "select_account"});
const api = window.DEAL_SNIPER_API ?? runtime.adminApiBase ?? runtime.apiBase ?? "";
let token = "";
let testedSourceKey = "";
let settingsDraft = null;
let proPublicationPreview = null;
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

function renderNewsFeeds(payload = {}) {
  const items = payload.items || [];
  byId("news-feeds").innerHTML = items.map((item) => `<article class="data-row"><div class="data-primary"><div><strong>${safe(item.publisher)}</strong>${statusPill(item.enabled ? "Enabled" : "Paused", item.enabled)}</div><div class="row-meta"><span>${safe(item.name)}</span><span>${number(item.sample_count)} validated items</span><a href="${safe(item.url)}" target="_blank" rel="noopener">Open feed</a></div></div><div class="row-actions"><button class="secondary toggle-news-feed" data-name="${safe(item.name)}" data-enabled="${item.enabled}">${item.enabled ? "Pause" : "Enable"}</button><button class="danger-button remove-news-feed" data-name="${safe(item.name)}">Remove</button></div></article>`).join("") || '<div class="empty-state">No custom news feeds. The environment baseline is used when configured.</div>';
  document.querySelectorAll(".toggle-news-feed").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try { await call(`/admin/news-feeds/${encodeURIComponent(button.dataset.name)}`, {method: "POST", body: JSON.stringify({enabled: button.dataset.enabled !== "true"})}); await refresh(); }
    catch (error) { showError(error); button.disabled = false; }
  }));
  document.querySelectorAll(".remove-news-feed").forEach((button) => button.addEventListener("click", async () => {
    if (!window.confirm(`Remove news feed ${button.dataset.name}? Publication history will be kept.`)) return;
    button.disabled = true;
    try { await call(`/admin/news-feeds/${encodeURIComponent(button.dataset.name)}/remove`, {method: "POST"}); await refresh(); }
    catch (error) { showError(error); button.disabled = false; }
  }));
}

async function addNewsFeed() {
  const name = byId("news-feed-name").value.trim().toLowerCase();
  const publisher = byId("news-feed-publisher").value.trim();
  const url = byId("news-feed-url").value.trim();
  const result = byId("news-feed-result");
  if (!/^[a-z][a-z0-9_-]{2,39}$/.test(name)) { showError(new Error("Use 3–40 lowercase letters, numbers, _ or - for the feed name.")); return; }
  if (publisher.length < 2 || !url.startsWith("https://")) { showError(new Error("Enter a publisher and a public HTTPS RSS or Atom URL.")); return; }
  byId("add-news-feed").disabled = true; result.textContent = "Validating fresh automotive items…";
  try {
    const response = await call("/admin/news-feeds", {method: "POST", body: JSON.stringify({name, publisher, url})});
    result.className = "test-good"; result.textContent = `${number(response.feed.sample_count)} relevant items validated. Feed enabled.`;
    byId("news-feed-name").value = ""; byId("news-feed-publisher").value = ""; byId("news-feed-url").value = "";
    await refresh();
  } catch (error) { result.className = "test-bad"; result.textContent = error instanceof Error ? error.message : String(error); }
  finally { byId("add-news-feed").disabled = false; }
}

function renderCloud(cloud = {}) {
  const groups = [["Scheduler", cloud.scheduler], ["Task queues", cloud.queues], ["Cloud Run", cloud.services]];
  byId("cloud").innerHTML = groups.map(([label, items]) => {
    const values = Array.isArray(items) ? items : [];
    const unavailable = values.some((item) => item.state === "UNAVAILABLE");
    const body = unavailable ? '<div class="empty-state error-state">Status unavailable. Check runtime viewer permissions.</div>' : values.map((item) => { const name = shortName(item.name); const controls = label === "Scheduler" ? `<div class="row-actions"><button class="secondary scheduler-action" data-job="${safe(name)}" data-action="run">Run now</button><button class="secondary scheduler-action" data-job="${safe(name)}" data-action="${item.state === "PAUSED" ? "resume" : "pause"}">${item.state === "PAUSED" ? "Resume" : "Pause"}</button></div>` : statusPill(item.state || (item.latestReadyRevision ? "Ready" : "Active"), true); return `<div class="brief-row"><div><strong>${safe(name)}</strong>${label === "Scheduler" ? statusPill(item.state || "Unknown", item.state !== "PAUSED") : ""}</div>${controls}</div>`; }).join("") || '<div class="empty-state">No resources found.</div>';
    return `<section class="admin-card"><div class="card-heading"><div><p class="eyebrow">GOOGLE CLOUD</p><h2>${safe(label)}</h2></div>${statusPill(unavailable ? "Unavailable" : "Connected", !unavailable)}</div>${body}</section>`;
  }).join("");
  document.querySelectorAll(".scheduler-action").forEach((button) => button.addEventListener("click", () => changeScheduler(button.dataset.job, button.dataset.action)));
}

async function changeScheduler(job, action) {
  const required = `${action.toUpperCase()} ${job}`;
  const confirmation = window.prompt(`This changes a live schedule. Type exactly: ${required}`);
  if (confirmation !== required) return;
  try { await call(`/admin/schedulers/${encodeURIComponent(job)}/action`, {method: "POST", body: JSON.stringify({action, operation_id: crypto.randomUUID(), confirmation})}); await refresh(); }
  catch (error) { showError(error); }
}

function renderRuns(payload = {}) {
  byId("runs").innerHTML = (payload.items || []).map((item) => `<article class="data-row"><div class="data-primary"><strong>${safe(item.source || item.event_type)}</strong><div class="row-meta"><span>${safe(item.success === true ? "Successful" : item.success === false ? "Failed" : "Recorded")}</span><span>${number(item.fetched)} fetched</span><span>${safe(item.duration_seconds || "—")} sec</span></div>${item.error ? `<span class="source-error">${safe(item.error)}</span>` : ""}</div></article>`).join("") || '<div class="empty-state">No runs recorded.</div>';
}

function renderListings(payload = {}) {
  byId("listings").innerHTML = (payload.items || []).map((item) => `<article class="data-row"><div class="data-primary"><strong>${safe(item.title)}</strong><div class="row-meta"><span>${safe(item.source)}</span><span>${money(item.price_aed)}</span><span>${safe(item.year || "Year unknown")}</span></div></div><a class="button secondary" href="${safe(item.url)}" target="_blank" rel="noopener">Open listing</a></article>`).join("") || '<div class="empty-state">No current listings.</div>';
}

function renderDecisions(payload = {}) {
  byId("decisions").innerHTML = (payload.items || []).map((item) => `<article class="data-row"><div class="data-primary"><div><strong>${safe(item.title)}</strong>${statusPill(item.action, ["CONTACT", "INSPECT"].includes(item.action))}</div><div class="row-meta"><span>${money(item.price_aed)}</span><span>Profit ${money(item.expected_profit_aed)}</span><span>ROI ${safe(item.roi_percent || "—")}%</span><span>${number(item.comparables_count)} comparables</span></div><span class="muted">Config ${safe(item.financial_config_version)} · Engine ${safe(item.engine_version)}</span></div></article>`).join("") || '<div class="empty-state">No current decisions.</div>';
}

function renderUsers(payload = {}) {
  byId("users").innerHTML = (payload.items || []).map((item) => `<article class="data-row"><div class="data-primary"><div><strong>User ${safe(item.user_id)}</strong>${statusPill(item.tariff || "free", item.tariff === "pro")}</div><div class="row-meta"><span>${safe(item.language_code || "en").toUpperCase()}</span><span>${safe((item.makes || []).join(", ") || "All makes")}</span><span>${safe((item.models || []).join(", ") || "All models")}</span></div></div></article>`).join("") || '<div class="empty-state">No user profiles recorded.</div>';
}

function renderErrors(payload = {}) {
  byId("errors-list").innerHTML = (payload.items || []).map((item) => `<article class="data-row"><div class="data-primary"><div><strong>${safe(item.id)}</strong>${statusPill(item.kind, false)}</div><span class="source-error">${safe(item.message || "No detail")}</span></div></article>`).join("") || '<div class="empty-state">No operational errors require attention.</div>';
}

function settingsPayload() {
  return {
    pro_price_aed: Number(byId("price-aed").value),
    pro_price_stars: Number(byId("price-stars").value),
    target_profit_aed: byId("target-profit").value,
    min_roi_percent: byId("min-roi").value,
    min_comparables_count: Number(byId("min-comparables").value),
    channel_max_posts_per_run: Number(byId("posts-per-run").value),
    pro_deals_enabled: byId("pro-deals-enabled").checked,
    pro_news_enabled: byId("pro-news-enabled").checked,
    pro_news_max_items: Number(byId("news-items-per-digest").value),
    pro_news_min_interval_hours: Number(byId("news-interval-hours").value),
    pro_news_ai_summary_enabled: byId("pro-news-ai-enabled").checked,
    operation_id: crypto.randomUUID(),
    confirmation: "",
  };
}

function renderSettings(payload = {}) {
  const active = payload.active || {};
  byId("active-settings").innerHTML = keyValues({version: active.version, commercial_price_aed: active.pro_price_aed, telegram_charge_stars: active.pro_price_stars, subscription_link: active.pro_subscription_url, target_profit_aed: active.target_profit_aed, min_roi_percent: active.min_roi_percent, min_comparables: active.min_comparables_count, posts_per_run: active.channel_max_posts_per_run, deal_cards: active.pro_deals_enabled, automotive_news: active.pro_news_enabled, news_items: active.pro_news_max_items, news_interval_hours: active.pro_news_min_interval_hours, vertex_intro: active.pro_news_ai_summary_enabled, activated_by: active.created_by});
  [["price-aed", active.pro_price_aed], ["price-stars", active.pro_price_stars], ["target-profit", active.target_profit_aed], ["min-roi", active.min_roi_percent], ["min-comparables", active.min_comparables_count], ["posts-per-run", active.channel_max_posts_per_run], ["news-items-per-digest", active.pro_news_max_items], ["news-interval-hours", active.pro_news_min_interval_hours]].forEach(([id, value]) => { if (document.activeElement !== byId(id)) byId(id).value = value ?? ""; });
  [["pro-deals-enabled", active.pro_deals_enabled], ["pro-news-enabled", active.pro_news_enabled], ["pro-news-ai-enabled", active.pro_news_ai_summary_enabled]].forEach(([id, value]) => { if (document.activeElement !== byId(id)) byId(id).checked = Boolean(value); });
  byId("settings-history").innerHTML = (payload.revisions || []).map((item) => `<article class="data-row ${item.state === "active" ? "revision-active" : ""}"><div class="data-primary"><div><strong>${safe(item.version)}</strong>${statusPill(item.state, item.state === "active")}</div><div class="row-meta"><span>${money(item.pro_price_aed)}</span><span>${number(item.pro_price_stars)} Stars</span><span>${safe(item.created_by)}</span></div></div>${item.state === "archived" ? `<button class="secondary rollback-settings" data-version="${safe(item.version)}">Rollback</button>` : ""}</article>`).join("") || '<div class="empty-state">Environment baseline is active; no revisions yet.</div>';
  document.querySelectorAll(".rollback-settings").forEach((button) => button.addEventListener("click", () => rollbackSettings(button.dataset.version)));
}

async function previewSettings() {
  try {
    settingsDraft = settingsPayload();
    const preview = await call("/admin/settings/preview", {method: "POST", body: JSON.stringify(settingsDraft)});
    const box = byId("settings-preview"); box.hidden = false; box.innerHTML = `<strong>Validated change</strong><span>${money(preview.current.pro_price_aed)} → ${money(preview.candidate.pro_price_aed)}; ${number(preview.current.pro_price_stars)} → ${number(preview.candidate.pro_price_stars)} Stars.</span><span>${preview.creates_new_telegram_link ? "A new Telegram paid link will be created." : "The existing paid link will remain active."}</span><span>Confirmation: ${safe(preview.confirmation_required)}</span>`;
    byId("apply-settings").disabled = false;
  } catch (error) { settingsDraft = null; byId("apply-settings").disabled = true; showError(error); }
}

async function applySettings() {
  if (!settingsDraft) return;
  const required = `APPLY ${settingsDraft.pro_price_stars} STARS`;
  const confirmation = window.prompt(`This changes the live Pro offer. Type exactly: ${required}`);
  if (confirmation !== required) { showError(new Error("The confirmation did not match. Nothing was changed.")); return; }
  byId("apply-settings").disabled = true;
  try { await call("/admin/settings/apply", {method: "POST", body: JSON.stringify({...settingsDraft, confirmation})}); settingsDraft = null; await refresh(); }
  catch (error) { showError(error); byId("apply-settings").disabled = false; }
}

async function rollbackSettings(version) {
  const required = `ROLLBACK ${version}`;
  const confirmation = window.prompt(`Rollback creates a new paid link and active revision. Type exactly: ${required}`);
  if (confirmation !== required) return;
  try { await call("/admin/settings/rollback", {method: "POST", body: JSON.stringify({version, operation_id: crypto.randomUUID(), confirmation})}); await refresh(); }
  catch (error) { showError(error); }
}

function render(data, pulse, preview, unknown, failed) {
  const sourceEntries = Object.entries(data.source_switches || {});
  const sourceHealthy = sourceEntries.filter(([name, enabled]) => sourceState(data.sources?.[name], enabled).good).length;
  byId("overview").innerHTML = metric("Listings stored", number(data.snapshot_count), "immutable snapshots") + metric("Sources healthy", `${sourceHealthy}/${sourceEntries.length}`, "installed adapters") + metric("Delivery", data.delivery_enabled ? "Running" : "Paused", "Telegram publishing") + metric("Schema", `v${data.schema_version}`, "production data");
  renderSources(data); renderCloud(data.cloud);
  byId("operations").innerHTML = keyValues(data.operations);
  byId("pulse").textContent = pulse.text || pulse.summary || "No market update is currently available.";
  byId("free").textContent = preview.free || "No current deal."; byId("pro").textContent = preview.pro || "No current deal.";
  byId("queue-brief").innerHTML = keyValues({delivery: data.delivery_enabled ? "running" : "paused", unknown: unknown.length, failed_history: failed.length, whatsapp: data.whatsapp_status});
  byId("subscription-brief").innerHTML = keyValues({price: money(data.subscription?.price_aed), active: data.subscription?.active || 0, total: data.subscription?.total || 0});
  byId("business-metrics").innerHTML = metric("Monthly price", money(data.subscription?.price_aed), "per Pro subscriber") + metric("Active Pro", number(data.subscription?.active), "Telegram subscriptions") + metric("Referrals", number(data.referrals?.total), "recorded invitations") + metric("WhatsApp", data.whatsapp_status, "channel relay");
  byId("financial").innerHTML = keyValues({...data.financial_config, pro_price_aed: data.subscription?.price_aed});
  const unknownRows = unknown.map((item) => `<article class="data-row"><div class="data-primary"><div><strong>${safe(item.delivery_id)}</strong>${statusPill("unknown", false)}</div><span class="source-error">${safe(item.last_error || "Ambiguous delivery result")}</span></div><div class="row-actions">${["mark_sent", "mark_failed", "retry_once"].map((action) => `<button class="secondary reconcile" data-id="${safe(item.delivery_id)}" data-action="${action}">${safe(action.replaceAll("_", " "))}</button>`).join("")}</div></article>`).join("");
  const failedRows = failed.map((item) => `<article class="data-row"><div class="data-primary"><div><strong>${safe(item.delivery_id)}</strong>${statusPill("failed history", false)}</div><span class="source-error">${safe(item.last_error || "Delivery failed")}</span><span class="muted">Historical failed records are diagnostic only. Reconciliation is available only for unknown delivery.</span></div></article>`).join("");
  byId("unknown").innerHTML = unknownRows + failedRows || '<div class="empty-state">No delivery exceptions. Everything is reconciled.</div>';
  document.querySelectorAll(".reconcile").forEach((button) => button.addEventListener("click", () => reconcile(button.dataset.id, button.dataset.action)));
}

function showError(caught) { byId("error").hidden = false; byId("error").textContent = caught instanceof Error ? caught.message : String(caught); }
async function reconcile(deliveryId, action) { try { await call(`/admin/outbox/${encodeURIComponent(deliveryId)}/reconcile`, {method: "POST", body: JSON.stringify({action})}); await refresh(); } catch (error) { showError(error); } }
function renderProPublications(payload = {}) {
  proPublicationPreview = payload;
  byId("pro-publication-status").innerHTML = keyValues({publishable: payload.publishable, delivered: payload.sent, pending: payload.pending, sending: payload.sending, unknown: payload.unknown, failed: payload.failed, missing: payload.missing, batch_limit: payload.batch_limit, last_reconciliation: payload.last_reconciliation?.created_at || "Never"});
  const news = payload.news || {};
  byId("pro-news-publication-status").innerHTML = keyValues({enabled: news.enabled, feeds: news.feeds, fetched: news.fetched, unpublished: news.unpublished, pending: news.pending, sent: news.sent, failed: news.failed, interval_open: news.interval_open, ai_intro_used: news.ai_used, last_reconciliation: payload.last_news_reconciliation?.created_at || "Never"});
  byId("publish-pro").disabled = !Number(payload.pending_actions || 0);
}

async function publishProNow() {
  const count = Number(proPublicationPreview?.pending_actions || 0);
  if (!count) return;
  const required = `PUBLISH ${count} PRO`;
  const confirmation = window.prompt(`This starts the idempotent publisher job for up to ${count} Pro publication(s). Type exactly: ${required}`);
  if (confirmation !== required) return;
  byId("publish-pro").disabled = true;
  try {
    const result = await call("/admin/pro-publications/run", {method: "POST", body: JSON.stringify({operation_id: crypto.randomUUID(), confirmation})});
    const box = byId("pro-publication-result"); box.hidden = false;
    box.innerHTML = `<strong>${result.started ? "Publisher started" : "Nothing to publish"}</strong><span>Selected by preview: ${number(result.preview?.publishable)}; missing: ${number(result.preview?.missing)}; pending: ${number(result.preview?.pending)}.</span>`;
    window.setTimeout(refresh, 5000);
  } catch (error) { showError(error); byId("publish-pro").disabled = false; }
}
async function refresh() {
  byId("error").hidden = true; byId("refresh").disabled = true;
  try {
    const requests = [call("/admin/overview"), call("/content/market-pulse"), call("/admin/preview"), call("/admin/outbox?state=unknown"), call("/admin/outbox?state=failed"), call("/admin/runs"), call("/admin/listings"), call("/admin/decisions"), call("/admin/users"), call("/admin/errors"), call("/admin/settings"), call("/admin/pro-publications"), call("/admin/news-feeds")];
    const [overviewResult, pulseResult, previewResult, unknownResult, failedResult, runsResult, listingsResult, decisionsResult, usersResult, errorsResult, settingsResult, proPublicationsResult, newsFeedsResult] = await Promise.allSettled(requests);
    if (overviewResult.status === "rejected") throw overviewResult.reason;
    const pulse = pulseResult.status === "fulfilled" ? pulseResult.value : {};
    const preview = previewResult.status === "fulfilled" ? previewResult.value : {};
    const unknown = unknownResult.status === "fulfilled" ? unknownResult.value : {items: []};
    const failed = failedResult.status === "fulfilled" ? failedResult.value : {items: []};
    render(overviewResult.value, pulse, preview, unknown.items || [], failed.items || []);
    if (runsResult.status === "fulfilled") renderRuns(runsResult.value); if (listingsResult.status === "fulfilled") renderListings(listingsResult.value); if (decisionsResult.status === "fulfilled") renderDecisions(decisionsResult.value); if (usersResult.status === "fulfilled") renderUsers(usersResult.value); if (errorsResult.status === "fulfilled") renderErrors(errorsResult.value); if (settingsResult.status === "fulfilled") renderSettings(settingsResult.value);
    if (proPublicationsResult.status === "fulfilled") renderProPublications(proPublicationsResult.value);
    if (newsFeedsResult.status === "fulfilled") renderNewsFeeds(newsFeedsResult.value);
    const partialErrors = [pulseResult, previewResult, unknownResult, failedResult, runsResult, listingsResult, decisionsResult, usersResult, errorsResult, settingsResult, proPublicationsResult, newsFeedsResult].filter((result) => result.status === "rejected");
    if (partialErrors.length) showError(new Error(`${partialErrors.length} section(s) are temporarily unavailable. Refresh will retry them.`));
    byId("updated").textContent = `Updated ${new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}`;
  } catch (error) { showError(error); } finally { byId("refresh").disabled = false; }
}

document.querySelectorAll(".admin-nav button").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".admin-nav button").forEach((item) => item.classList.toggle("active", item === button));
  document.querySelectorAll(".admin-view").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === button.dataset.view));
  byId("page-title").textContent = button.textContent;
}));
function googleAuthMessage(error) {
  if (error?.code === "auth/account-exists-with-different-credential") return "This email still has an old password-only Firebase account. The administrator account must be migrated before Google sign-in can continue.";
  if (error?.code === "auth/unauthorized-domain") return "This Hosting domain is not authorized for Firebase Authentication.";
  if (error?.code === "auth/popup-blocked") return "The Google popup was blocked. Use Continue in this window.";
  if (error?.code === "auth/popup-closed-by-user") return "Google sign-in was cancelled.";
  return error instanceof Error ? error.message : String(error);
}

byId("login").addEventListener("click", async () => {
  byId("error").hidden = true;
  byId("login").disabled = true;
  try {
    await signInWithPopup(auth, googleProvider);
  } catch (error) {
    if (error?.code === "auth/popup-blocked") byId("login-redirect").hidden = false;
    showError(new Error(googleAuthMessage(error)));
  } finally { byId("login").disabled = false; }
});
byId("login-redirect").addEventListener("click", async () => {
  byId("error").hidden = true;
  byId("login-redirect").disabled = true;
  try { await signInWithRedirect(auth, googleProvider); }
  catch (error) { showError(new Error(googleAuthMessage(error))); byId("login-redirect").disabled = false; }
});
byId("logout").addEventListener("click", () => signOut(auth)); byId("refresh").addEventListener("click", refresh);
byId("test-source").addEventListener("click", testNewSource); byId("add-source").addEventListener("click", addNewSource);
byId("add-news-feed").addEventListener("click", addNewsFeed);
byId("preview-settings").addEventListener("click", previewSettings); byId("apply-settings").addEventListener("click", applySettings);
byId("publish-pro").addEventListener("click", publishProNow);
[byId("source-name"), byId("source-url")].forEach((input) => input.addEventListener("input", () => { testedSourceKey = ""; byId("add-source").disabled = true; }));
getRedirectResult(auth).catch((error) => showError(new Error(googleAuthMessage(error))));
onAuthStateChanged(auth, async (user) => {
  if (!user) {
    token = ""; byId("identity").textContent = "Not signed in"; byId("login").hidden = false; byId("logout").hidden = true; byId("refresh").disabled = true; byId("auth-notice").hidden = false;
    return;
  }
  try {
    token = await user.getIdToken(); byId("identity").textContent = user.email || "Administrator"; byId("login").hidden = true; byId("login-redirect").hidden = true; byId("logout").hidden = false; byId("auth-notice").hidden = true; byId("refresh").disabled = false; await refresh();
  } catch (error) {
    token = ""; byId("refresh").disabled = true;
    showError(new Error("Firebase session could not be established. Reload the page and sign in again."));
  }
});
