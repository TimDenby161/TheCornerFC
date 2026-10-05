// Methodology page: fills the live sections from data/methodology.json. Everything is built with
// textContent, never innerHTML, so nothing in the data is treated as markup.
"use strict";

const STALE_HOURS = 36;   // the nightly run plus a margin: older than this, say so

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const c of children) if (c != null) node.append(c);
  return node;
}

const when = (iso) => new Date(iso).toLocaleString("en-GB",
  { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
const day = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
const pct = (x) => `${(x * 100).toFixed(1)}%`;
const num = (x) => x.toLocaleString("en-GB");

function stat(value, label) {
  return el("div", { className: "stat" }, el("span", { className: "stat-v", textContent: value }),
    el("span", { className: "stat-l", textContent: label }));
}

function fill(id, ...nodes) {
  const box = document.getElementById(id);
  box.replaceChildren(...nodes.filter((n) => n != null));
}

function note(text, cls = "muted") {
  return el("p", { className: cls, textContent: text });
}

// How much weight a sample can bear, in words
function sampleNote(n, what) {
  if (n < 500) return note(`Very early: ${num(n)} ${what} is far too few to judge the model. These figures will move a lot as more come in.`, "warn");
  if (n < 2000) return note(`Still a small sample (${num(n)} ${what}). Small differences are likely to be luck.`, "warn");
  return null;
}

function period(p) {
  return p ? `Kick-offs from ${day(p.from)} to ${day(p.to)}.` : "";
}

function versions(vs, what) {
  if (!vs || !vs.length) return null;
  const list = vs.map((v) => `${v.name} (${num(v.n)})`).join(", ");
  return note(vs.length === 1 ? `All ${what} from model version ${list}.` : `Pooled across model versions: ${list}.`);
}

function renderFreshness(d) {
  const f = d.freshness || {};
  const rows = [
    ["Site data exported", d.generated_at],
    ["Predictions last written", f.predictions],
    ["Injury lists last fetched", f.injuries],
    ["Odds last fetched", f.odds],
  ].filter(([, iso]) => iso);
  const items = rows.map(([label, iso]) => el("li", {}, el("strong", { textContent: `${label}: ` }), when(iso)));
  const hours = (Date.now() - new Date(d.generated_at)) / 36e5;
  fill("fresh-live",
    el("ul", { className: "fresh" }, ...items),
    hours > STALE_HOURS ? note(`This data is ${Math.floor(hours)} hours old, so an update has been missed. Treat predictions and injury news with extra care.`, "warn") : null,
    note("Times are in your time zone."));
}

function calibrationTable(bins) {
  const rows = bins.map(([bin, n, mean, seen]) => {
    const [lo, hi] = bin.split("-").map((x) => Math.round(x * 100));
    return el("tr", {}, el("td", { textContent: `${lo}–${hi}%` }), el("td", { textContent: `${Math.round(mean * 100)}%` }),
      el("td", { textContent: `${Math.round(seen * 100)}%` }), el("td", { textContent: num(n) }));
  });
  const head = el("tr", {}, ...["Model said", "Average", "It happened", "Predictions"].map((t) => el("th", { textContent: t })));
  return el("table", { className: "calib" }, el("thead", {}, head), el("tbody", {}, ...rows));
}

function renderMatches(m) {
  if (!m) {
    fill("matches-live", note("No live predictions have been scored yet. Figures appear here once matches predicted before kick-off have finished."));
    return;
  }
  fill("matches-live",
    note(`${num(m.n)} finished matches, each predicted before kick-off. ${period(m.period)}`, ""),
    sampleNote(m.n, "matches"),
    el("div", { className: "stats" },
      stat(pct(m.accuracy), "Most likely result was right"),
      stat(m.log_loss.toFixed(3), "Log loss (lower is better)"),
      stat(m.brier.toFixed(3), "Brier score (lower is better)"),
      m.exact_score && m.exact_score.n ? stat(pct(m.exact_score.accuracy), "Exact score right") : null),
    note("Giving every result a one-in-three chance would score 1.099 and 0.667."),
    el("p", {}, el("strong", { textContent: "Calibration" }), ": when the model gave something a certain chance, how often did it happen?"),
    calibrationTable(m.calibration),
    note("Rows with few predictions say little on their own."),
    versions(m.versions, "predictions are"),
    m.excluded_no_regulation_score ? note(`${num(m.excluded_no_regulation_score)} matches without a 90-minute score on record are left out.`) : null);
}

function renderLineups(l) {
  if (!l) {
    fill("lineups-live", note("No live predicted line-ups have been scored yet. They need a prediction saved before the team sheet came out, and the official XI afterwards."));
    return;
  }
  fill("lineups-live",
    note(`${num(l.n)} team line-ups predicted before the official team sheet was published. ${period(l.period)}`, ""),
    sampleNote(l.n, "line-ups"),
    el("div", { className: "stats" },
      stat(`${l.correct_starters_mean.toFixed(1)} of 11`, "Starters named correctly, on average"),
      l.role_accuracy && l.role_accuracy.n ? stat(pct(l.role_accuracy.accuracy), "Correct starters in the right position") : null),
    versions(l.versions, "line-ups are"),
    l.excluded_no_official_xi ? note(`${num(l.excluded_no_official_xi)} line-ups are left out because no complete official XI was recorded.`) : null);
}

function renderVersion(d) {
  const model = (d.freshness || {}).model;
  fill("version-live", model
    ? el("p", {}, "The match model in use is ", el("strong", { textContent: model.name }),
      model.code ? ` (code ${model.code})` : "", model.registered ? `, registered ${day(model.registered)}.` : ".")
    : note("The current model version isn't available in this data export."));
}

async function main() {
  try {
    // from the database or the published file (data.js); the file if the database doesn't answer
    const file = async () => {
      const res = await fetch("data/methodology.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      return res.json();
    };
    const d = DATA_SOURCE === "db" ? await siteDoc("methodology").catch(file) : await file();
    renderFreshness(d);
    renderMatches(d.matches);
    renderLineups(d.lineups);
    renderVersion(d);
  } catch (err) {
    console.error(err);
    for (const id of ["fresh-live", "matches-live", "lineups-live", "version-live"]) {
      fill(id, note("Couldn't load the live figures. Try reloading the page.", "warn"));
    }
  }
}

main();
