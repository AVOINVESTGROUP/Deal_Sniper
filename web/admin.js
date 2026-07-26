import { initializeApp } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import { getAuth, GoogleAuthProvider, signInWithPopup } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";

const config = await (await fetch("/__/firebase/init.json")).json();
const auth = getAuth(initializeApp(config));
const runtime = await (await fetch("/runtime-config.json")).json();
const api = window.DEAL_SNIPER_API || runtime.apiBase || "";
let token = "";
const error = document.querySelector("#error");

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
    document.querySelector("#operations").textContent = JSON.stringify({ operations: data.operations, financial_config: data.financial_config }, null, 2);
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

document.querySelector("#login").onclick = async () => {
  const result = await signInWithPopup(auth, new GoogleAuthProvider());
  token = await result.user.getIdToken();
  document.querySelector("#identity").textContent = result.user.email;
  document.querySelector("#refresh").disabled = false;
  await refresh();
};
document.querySelector("#refresh").onclick = refresh;
