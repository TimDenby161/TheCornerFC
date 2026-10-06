"use strict";

// Where the site's data comes from: the database. The export writes every data file as a row of
// the site.docs table, keyed by the file's path without ".json" ("matches", "clubs/42"). The
// table can't be read directly: site_doc() returns one row by its key
// (db/migrations/20261005_site_doc_cache.sql). There are no data files on the published site.
// ?data=files in the address reads data/ beside the page instead, for a local copy that has its
// own export there; ?data=db says the default out loud.
// The key below is Supabase's public key: on its own the database lets it call nothing but the
// functions granted to it (site_doc here; the owner-only FPL data and the accounts in app.js).
const SUPABASE = { url: "https://bookkurhdabdeccckjbn.supabase.co", key: "sb_publishable_JZ_oJVHIO75SFbFc95LQew_3wmKuvM7" };
const DATA_SOURCE = (() => {
  const asked = new URLSearchParams(location.search).get("data");
  return asked === "db" || asked === "files" ? asked : "db";
})();

// One row of site.docs. A plain GET with the key in the address, so the browser sends no preflight
// and can keep the answer: with the row's content hash (from the "manifest" row) the database
// says to keep it for a year, since the address changes when the content does; without one it
// says to ask again each time. A key with no row answers null, which is this site's "not found"
// (missing); any other failure, the function not being there included, is the database's.
// A subscriber's requests carry their sign-in, so the database can give them the paid rows
// (db/migrations/20261006_paid_tier.sql). Only theirs: PAID_KEY is set once the database has said
// this account subscribes and the paywall is on (app.js, refreshSubscription), so every other
// visitor's requests stay the plain GETs described below. The token is read from where the
// sign-in library keeps the session (AUTH_STORE, its storageKey in app.js); one about to run out
// isn't sent, since the database refuses a stale one outright.
const PAID_KEY = "fc.paid", AUTH_STORE = "fc.auth";
function siteAuth() {
  try {
    if (localStorage.getItem(PAID_KEY) !== "1") return {};
    const kept = JSON.parse(localStorage.getItem(AUTH_STORE) || "null");
    return kept?.access_token && kept.expires_at * 1000 > Date.now() + 30000 ? { Authorization: `Bearer ${kept.access_token}` } : {};
  } catch { return {}; }
}

// A database function that answers one page's question from the tables themselves, such as
// site_lineups (one match's line-ups, db/migrations/20261005_site_lineups.sql). Fixed SQL on the
// database's side; params are its arguments. Nothing is prepared in advance and nothing is kept.
// A plain GET like site_doc's; arguments too long for an address (a few thousand ids) are posted.
async function siteAsk(fn, params) {
  const q = String(new URLSearchParams({ ...params, apikey: SUPABASE.key }));
  const r = await askDatabase(() => q.length < 8000 ? fetch(`${SUPABASE.url}/rest/v1/rpc/${fn}?${q}`, { headers: siteAuth() })
    : fetch(`${SUPABASE.url}/rest/v1/rpc/${fn}?apikey=${SUPABASE.key}`,
      { method: "POST", headers: { "Content-Type": "application/json", ...siteAuth() }, body: JSON.stringify(params) }));
  if (!r.ok) throw Object.assign(new Error(`${fn}: ${r.status}`), { status: r.status });
  return r.json();
}
// The database is the only source, so a request that fails outright or with a server error (a
// dropped connection, a busy moment) is sent once more after a moment before the view gives up.
async function askDatabase(send) {
  for (let again = false; ; again = true) {
    try {
      const r = await send();
      if (r.status < 500 || again) return r;
    } catch (err) {
      if (again) throw err;
    }
    await new Promise((done) => setTimeout(done, 400));
  }
}

async function siteDoc(key, hash) {
  const q = new URLSearchParams({ p_key: key, apikey: SUPABASE.key });
  if (hash) q.set("p_v", hash);
  const r = await askDatabase(() => fetch(`${SUPABASE.url}/rest/v1/rpc/site_doc?${q}`));
  if (!r.ok) throw Object.assign(new Error(`${key}: ${r.status}`), { status: r.status });
  const doc = await r.json();
  if (doc === null) throw Object.assign(new Error(`${key}: 404`), { status: 404, missing: true });
  return doc;
}
