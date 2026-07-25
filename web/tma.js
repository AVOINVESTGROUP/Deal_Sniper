import { initializeApp } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import { getAuth, signInWithCustomToken } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";

const telegram = window.Telegram.WebApp;
telegram.ready();
telegram.expand();
const runtime = await (await fetch("/runtime-config.json")).json();
const api = runtime.apiBase || "";

async function authorized(path, token, options = {}) {
  const response = await fetch(api + path, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function recordOutcome(item, token) {
  const purchase = window.prompt("Actual purchase price, AED");
  if (purchase === null) return;
  const repair = window.prompt("Actual repair and other costs, AED", "0");
  const sale = window.prompt("Actual sale price, AED (leave blank if not sold)", "");
  const holdDays = window.prompt("Hold days", "0");
  await authorized("/tma/outcomes", token, {
    method: "POST",
    body: JSON.stringify({
      listing_id: `${item.listing.source}:${item.listing.source_listing_id}`,
      decision_content_hash: item.decision.content_hash,
      status: sale ? "sold" : "purchased",
      purchase_price_aed: purchase,
      actual_cost_aed: repair || "0",
      sale_price_aed: sale || null,
      hold_days: Number(holdDays || 0),
    }),
  });
  telegram.showAlert("Outcome saved");
}

async function toggleFavorite(item, token, button) {
  const listingId = `${item.listing.source}:${item.listing.source_listing_id}`;
  const favorite = button.dataset.favorite !== "true";
  await authorized("/tma/favorites", token, {
    method: "POST",
    body: JSON.stringify({ listing_id: listingId, favorite }),
  });
  button.dataset.favorite = String(favorite);
  button.textContent = favorite ? "Saved" : "Save";
}

try {
  const config = await (await fetch("/__/firebase/init.json")).json();
  const auth = getAuth(initializeApp(config));
  const exchange = await fetch(api + "/tma/auth", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ init_data: telegram.initData }),
  });
  if (!exchange.ok) throw new Error(await exchange.text());
  const custom = await exchange.json();
  const credential = await signInWithCustomToken(auth, custom.firebase_custom_token);
  const token = await credential.user.getIdToken();
  const data = await authorized("/tma/feed", token);
  document.querySelector("#state").textContent = `${data.items.length} current opportunities`;
  const feed = document.querySelector("#feed");
  for (const item of data.items) {
    const decision = item.decision;
    const listing = item.listing;
    const card = document.createElement("article");
    card.className = "card";
    const title = document.createElement("h2");
    title.textContent = listing.title;
    const summary = document.createElement("p");
    summary.textContent = `${listing.price_aed} AED · ${decision.action} · profit ${decision.expected_profit_aed ?? "—"} AED · ROI ${decision.roi_percent ?? "—"}%`;
    const link = document.createElement("a");
    link.href = listing.url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "Open listing";
    const favorite = document.createElement("button");
    favorite.textContent = "Save";
    favorite.dataset.favorite = "false";
    favorite.onclick = () => toggleFavorite(item, token, favorite);
    const outcome = document.createElement("button");
    outcome.textContent = "Record outcome";
    outcome.onclick = () => recordOutcome(item, token);
    card.append(title, summary, link, document.createTextNode(" "), favorite,
      document.createTextNode(" "), outcome);
    feed.append(card);
  }
} catch (error) {
  document.querySelector("#state").textContent = "Unavailable";
  document.querySelector("#error").textContent = error.message;
}
