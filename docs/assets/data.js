"use strict";

// Where the site's data comes from. The export publishes every data file twice: in data/ on
// GitHub Pages, and as a row of the database's site.docs table, keyed by the file's path without
// ".json" ("matches", "clubs/42"). The table can't be read directly: site_doc() returns one row by
// its key (db/migrations/20261005_site_doc_cache.sql). The site reads the database (since
// 2026-10-05), and the published file if the database doesn't answer; ?data=files in the address
// reads the files only, and ?data=db says the default out loud.
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
// A database function that answers one page's question from the tables themselves, such as
// site_lineups (one match's line-ups, db/migrations/20261005_site_lineups.sql). Fixed SQL on the
// database's side; params are its arguments. Nothing is prepared in advance and nothing is kept.
// A plain GET like site_doc's; arguments too long for an address (a few thousand ids) are posted.
async function siteAsk(fn, params) {
  const q = String(new URLSearchParams({ ...params, apikey: SUPABASE.key }));
  const r = q.length < 8000 ? await fetch(`${SUPABASE.url}/rest/v1/rpc/${fn}?${q}`)
    : await fetch(`${SUPABASE.url}/rest/v1/rpc/${fn}?apikey=${SUPABASE.key}`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params) });
  if (!r.ok) throw Object.assign(new Error(`${fn}: ${r.status}`), { status: r.status });
  return r.json();
}

async function siteDoc(key, hash) {
  const q = new URLSearchParams({ p_key: key, apikey: SUPABASE.key });
  if (hash) q.set("p_v", hash);
  const r = await fetch(`${SUPABASE.url}/rest/v1/rpc/site_doc?${q}`);
  if (!r.ok) throw Object.assign(new Error(`${key}: ${r.status}`), { status: r.status });
  const doc = await r.json();
  if (doc === null) throw Object.assign(new Error(`${key}: 404`), { status: 404, missing: true });
  return doc;
}
