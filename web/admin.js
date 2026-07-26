import { initializeApp } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import { getAuth, signInWithCustomToken } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";

const config = await (await fetch("/__/firebase/init.json")).json();
const auth = getAuth(initializeApp(config));
const runtime = await (await fetch("/runtime-config.json")).json();
const api = window.DEAL_SNIPER_API || runtime.apiBase || "";
let token = "";
const error = document.querySelector("#error");
const identity = document.querySelector("#identity");
const login = document.querySelector("#login");
const refreshButton = document.querySelector("#refresh");
const telegram = window.Telegram?.WebApp;

async function call(path, options = {}) {
  const response = await fetch(api + path, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options.headers },
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
}

async function reconcile(deliveryId, action) {
  await call(`/admin/outbox/${deliveryId}/reconcile`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
  await refresh();
}

async function refresh() {
  error.textContent = "";
  try {
    const [data, pulse, preview, unknown, failed] = await Promise.all([
      call("/admin/overview"), call("/content/market-pulse"),
      call("/admin/preview"), call("/admin/outbox?state=unknown"),
      call("/admin/outbox?state=failed"),
    ]);
    document.querySelector("#overview").innerHTML =
      `<div class=card><b>Snapshots</b><p>${data.snapshot_count}</p></div>` +
      `<div class=card><b>Delivery</b><p>${data.delivery_enabled}</p></div>` +
      `<div class=card><b>WhatsApp</b><p>${data.whatsapp_status}</p></div>` +
      `<div class=card><b>Schema</b><p>${data.schema_version}</p></div>`;
    const root = document.querySelector("#sources"); root.innerHTML = "";
    for (const [name, enabled] of Object.entries(data.source_switches)) {
      const row = document.createElement("p");
      const health = data.sources[name] || {};
      row.textContent = `${name}: ${enabled ? "enabled" : "disabled"}; ${JSON.stringify(health)} `;
      const button = document.createElement("button"); button.textContent = enabled ? "Disable" : "Enable";
      button.onclick = async () => { await call(`/admin/sources/${name}`, { method: "POST", body: JSON.stringify({ enabled: !enabled }) }); await refresh(); };
      row.append(button); root.append(row);
    }
    document.querySelector("#cloud").textContent = JSON.stringify(data.cloud, null, 2);
    document.querySelector("#operations").textContent = JSON.stringify({ operations: data.operations, financial_config: data.financial_config, subscription: data.subscription, referrals: data.referrals }, null, 2);
    document.querySelector("#pulse").textContent = JSON.stringify(pulse, null, 2);
    document.querySelector("#free").textContent = preview.free || "No current deal";
    document.querySelector("#pro").textContent = preview.pro || "No current deal";
    const unknownRoot = document.querySelector("#unknown"); unknownRoot.innerHTML = "";
    for (const item of [...unknown.items, ...failed.items]) {
      const row = document.createElement("p"); row.textContent = `${item.delivery_id} · ${item.last_error || "ambiguous result"} `;
      for (const action of ["mark_sent", "mark_failed", "retry_once"]) {
        const button = document.createElement("button"); button.textContent = action;
        button.onclick = () => reconcile(item.delivery_id, action); row.append(button);
      }
      unknownRoot.append(row);
    }
  } catch (caught) { error.textContent = caught.message; }
}

async function authenticateFromTelegram() {
  telegram?.ready();
  telegram?.expand();
  if (!telegram?.initData) {
    identity.textContent = "Open this panel from the administrator button in @DubaiDealSniper111_bot.";
    login.hidden = false;
    return;
  }
  login.hidden = true;
  identity.textContent = "Verifying Telegram administrator…";
  try {
    const exchange = await fetch(api + "/tma/auth", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({init_data: telegram.initData}),
    });
    if (!exchange.ok) throw new Error(`${exchange.status}: ${await exchange.text()}`);
    const custom = await exchange.json();
    const credential = await signInWithCustomToken(auth, custom.firebase_custom_token);
    token = await credential.user.getIdToken();
    identity.textContent = `Administrator ${telegram.initDataUnsafe?.user?.first_name || "verified"}`;
    refreshButton.disabled = false;
    await refresh();
  } catch (caught) {
    identity.textContent = "Administrator access failed.";
    error.textContent = caught.message;
  }
}

login.onclick = () => { window.location.href = "https://t.me/DubaiDealSniper111_bot?start=admin"; };
refreshButton.onclick = refresh;
await authenticateFromTelegram();
