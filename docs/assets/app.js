"use strict";

// Competition ids from API-Football. Chips shown on the first row; the rest go under "more".
const PRIMARY_COMPS = [
  { id: "eng", label: "English", ids: [39, 40, 41, 42, 43, 50, 51, 45, 46, 47, 48, 528] },
  { id: "39", label: "Prem" }, { id: "40", label: "Champ" }, { id: "41", label: "L1" },
  { id: "42", label: "L2" }, { id: "2", label: "UCL" }, { id: "3", label: "UEL" },
];
const TABLE_COMPS = [
  { id: "39", label: "Prem" }, { id: "40", label: "Champ" }, { id: "41", label: "L1" },
  { id: "42", label: "L2" }, { id: "140", label: "La Liga" }, { id: "135", label: "Serie A" },
  { id: "78", label: "Bundesliga" }, { id: "61", label: "Ligue 1" },
];
const SHORT_NAMES = {
  2: "Champions League", 3: "Europa League", 848: "Conference League", 531: "UEFA Super Cup",
  15: "Club World Cup", 45: "FA Cup", 48: "EFL Cup", 46: "EFL Trophy", 47: "FA Trophy",
  528: "Community Shield", 181: "Scottish Cup", 185: "Scottish League Cup",
};
// Order competition groups are stacked in on the Matches tab (anything else follows)
const GROUP_ORDER = [39, 40, 41, 42, 2, 3, 848, 45, 48, 46, 140, 135, 78, 61, 94, 88, 144, 179,
  43, 50, 51, 47];
const RATING_LABELS = { 1: "Terrible", 2: "Poor", 3: "Decent", 4: "Very good", 5: "Excellent" };
const FACTORS = [
  ["r_winner", "Winner", "30%"], ["r_margin", "Margin", "25%"], ["r_clean_sheets", "Clean sheets", "20%"],
  ["r_shape", "Shape", "15%"], ["r_goals", "Goals", "10%"],
];
const LIVE = new Set(["1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT", "SUSP"]);
const FINISHED = new Set(["FT", "AET", "PEN", "AWD", "WO"]);

// Remembered view choices (this browser only; storage can be blocked, so never required)
const storedFlag = (k) => { try { return localStorage.getItem(`fc.${k}`) === "1"; } catch { return false; } };
const storeFlag = (k, on) => { try { localStorage.setItem(`fc.${k}`, on ? "1" : "0"); } catch { /* not stored */ } };

const state = {
  data: null, rankings: null, compLabels: {},
  matchFilter: "all", tableFilter: "all", date: null,
  tableSort: "current", tableSearch: "", excluded: new Set(), collapsed: new Set(),
  stats: null, statsRange: "30d", statsFilter: "all",
  lineupRec: undefined, lineupHist: undefined, lineupSource: "live", lineupRange: "all", lineupFilter: "all", lineupShown: 50,
  lineupCountries: {},
  bets: null, betStrategy: "all", betMarket: "all", betView: "all", betFilter: "all", tipsCollapsed: new Set(),
  players: undefined, drawn: new Set(), tableView: "clubs", playerSort: null, ranges: {}, playerYears: storedFlag("playerYears"), ageMin: null, ageMax: null,
};

const $ = (sel) => document.querySelector(sel);
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function pad(n) { return String(n).padStart(2, "0"); }
function localDateStr(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }
function parseDateInput(v) { const [y, m, d] = v.split("-").map(Number); return new Date(y, m - 1, d); }
function fmtTime(iso) { return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }); }
function fmtDay(iso) { return new Date(iso).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }); }
function fmtShortDate(iso) { return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" }); }

// ------------------------------------------------------------------ data
const decodeEntities = (t) => typeof t === "string" && t.includes("&")
  ? t.replace(/&(apos|#39|quot|amp|lt|gt);/g, (_, e) => ({ apos: "'", "#39": "'", quot: '"', amp: "&", lt: "<", gt: ">" }[e])) : t;
function rowsToObjects(fields, rows) {
  return rows.map((r) => Object.fromEntries(fields.map((f, i) => [f, r[i]])));
}

// Every data file: revalidated with the server each time ("no-cache": a 304 when it hasn't
// changed, so the data is always current without downloading it again), and a file already on
// its way is shared rather than fetched twice
const inflight = new Map();
function getJson(path) {
  if (!inflight.has(path)) inflight.set(path, fetch(path, { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw Object.assign(new Error(`${path}: ${r.status}`), { status: r.status }); return r.json(); })
    .finally(() => inflight.delete(path)));
  return inflight.get(path);
}
// A file that isn't published yet (404) is "nothing yet"; any other failure (offline, a server
// error) is remembered, so the view says it couldn't load and offers a reload, not "check back tomorrow"
const failedLoads = new Set();
const getJsonOrNull = (path) => getJson(path).then((d) => { failedLoads.delete(path); return d; },
  (err) => { if (err.status !== 404) failedLoads.add(path); return null; });
const loadFailed = (...paths) => paths.some((p) => failedLoads.has(`data/${p}.json`));
const loadError = (what) => `<div class="empty-state" role="alert">Couldn't load ${what}. Check your connection, then <button type="button" class="link-btn" data-reload>reload the page</button>.</div>`;
document.addEventListener("click", (e) => { if (e.target.closest("[data-reload]")) location.reload(); });

// players.json is the largest file by far, so it's fetched the first time a view needs it (the
// Players table, club, player and nationality pages, line-ups and squad ratings on match cards,
// the team pop-up's predicted XI, and the player links on Nations and the fantasy tabs), not on
// every visit. state.players: undefined until then, null if the file couldn't be loaded
function loadPlayers() {
  return state.playersLoading ||= getJsonOrNull("data/players.json").then((pj) => {
    if (pj) {        // API-Football sends some names HTML-encoded ("O&apos;Reilly")
      for (const r of pj.players) r[1] = decodeEntities(r[1]);
      for (const xi of Object.values(pj.next_xi || {})) for (const r of xi.players) r[1] = decodeEntities(r[1]);
      for (const k of ["fixture_xi", "actual_xi", "prematch_xi"])
        for (const teams of Object.values(pj[k] || {})) for (const xi of Object.values(teams)) for (const r of xi) r[1] = decodeEntities(r[1]);
    }
    state.players = pj ? { list: rowsToObjects(pj.fields, pj.players), nextXi: pj.next_xi, fixtureXi: pj.fixture_xi || {},
      actualXi: pj.actual_xi || {}, prematchXi: pj.prematch_xi || {}, seasons: pj.seasons || [], futureSeasons: pj.future_seasons || [], teams: pj.teams || {} } : null;
  });
}

async function loadData() {
  try {
    // A page that opens on a view needing players.json asks for it alongside the rest, so the
    // largest file isn't left waiting behind them. The Players table waits for it, to be drawn once
    const hash = location.hash;
    const players = /^#\/(players|club\/|player\/|nation|fpl$|efl-fantasy$)/.test(hash) ? loadPlayers() : null;
    const [m, r, st, bets, fpl] = await Promise.all([
      getJson("data/matches.json"), getJson("data/rankings.json"), getJsonOrNull("data/stats.json"),
      getJsonOrNull("data/bets.json"), getJsonOrNull("data/fpl.json"), hash.startsWith("#/players") ? players : null,
    ]);
    state.stats = st;
    state.fpl = fpl;
    state.bets = bets;
    state.data = { ...m, matches: rowsToObjects(m.fields, m.matches) };
    state.rankings = rowsToObjects(r.fields, r.rankings);
    // Gap: Current Strength less Baseline Strength (as shown, so the sum adds up), how far a club's
    // rating now sits from its long-term level. Not recent movement: that is x.form, the export's
    // Elo change over the club's last 6 matches
    for (const x of state.rankings) x.trend = Math.round(x.current) - Math.round(x.lt);
    state.rankByTeam = new Map(state.rankings.map((x) => [x.team, x]));
    buildCompetitionLabels();
    renderFreshness();
    if (!state.date) state.date = defaultDate();
    renderTableFilters();
    renderStatsFilters();
    renderBetFilters();
    loadEuroCups();
    route();          // draws the tab that's open; the others are drawn when first opened (showTab)
    document.body.classList.remove("booting");
  } catch (err) {
    console.error(err);
    $("#boot-status").outerHTML = loadError("the site's data");
  }
}

// When the data behind the site last changed: the export time and whatever freshness the export
// sends (latest predictions, injuries, odds fetched, match model version); nothing else is shown
function renderFreshness() {
  const f = state.data.freshness || {};
  const when = (iso) => `${fmtShortDate(iso)} ${fmtTime(iso)}`;
  const item = (label, iso, tip) => iso ? `<span title="${escapeHtml(tip)}">${label} ${escapeHtml(when(iso))}</span>` : "";
  const model = f.model ? `<span title="${escapeHtml(`Latest registered match model version${f.model.registered ? `, registered ${when(f.model.registered)}` : ""}`)}">Model ${escapeHtml(f.model.name)}${f.model.code ? ` · ${escapeHtml(f.model.code)}` : ""}</span>` : "";
  const parts = [
    item("Data updated", state.data.generated_at, "When this site's data was last exported"),
    item("Predictions updated", f.predictions, "Latest match prediction written"),
    item("Injuries updated", f.injuries, "Latest injury and suspension list fetched"),
    item("Odds last seen", f.odds, "Latest bookmaker prices fetched"),
    model,
  ].filter(Boolean);
  const el = $("#freshness");
  el.innerHTML = parts.join("");
  el.hidden = !parts.length;
}

function buildCompetitionLabels() {
  const comps = state.data.competitions;
  const nameCount = {};
  Object.values(comps).forEach((c) => { nameCount[c.name] = (nameCount[c.name] || 0) + 1; });
  for (const [id, c] of Object.entries(comps)) {
    state.compLabels[id] = SHORT_NAMES[id]
      || (c.country === "England" || c.country === "World" || nameCount[c.name] === 1 ? c.name : `${c.name} (${c.country.replace(/-/g, " ")})`);
  }
}
const compLabel = (id) => state.compLabels[id] || `Competition ${id}`;
// "Country · League" after the team name, for rows that span leagues; both link to their pages
function countryLeague(id) {
  const c = state.data.competitions[id];
  if (!c) return "";
  return ` <span class="club-meta">${flagLink(c.country)}<span class="cm-league">${leagueLink(id)}</span></span>`;
}
// Shorter club names, for the Rankings rows where the full name and its flag don't fit on one line
const CLUB_SHORT = {
  157: "Bayern", 50: "Man City", 85: "PSG", 33: "Man Utd", 52: "Palace", 168: "Leverkusen",
  165: "Dortmund", 65: "Nott'm Forest", 530: "Atlético", 569: "Club Brugge", 1393: "Union SG",
  553: "Olympiakos", 167: "Hoffenheim", 169: "Frankfurt", 728: "Rayo", 134: "Athletico-PR",
  1603: "Vancouver", 106: "Brest", 163: "Gladbach", 558: "Spartak", 397: "Midtjylland",
  3402: "Omonia", 651: "Ferencváros", 398: "Nordsjælland", 598: "Crvena Zvezda", 550: "Shakhtar",
  2278: "Chivas", 180: "Heidenheim", 1616: "LAFC", 458: "Argentinos", 571: "Salzburg",
  437: "Rosario", 2932: "Al-Hilal", 450: "Estudiantes", 339: "Legia", 238: "Viseu",
  364: "Djurgården", 3491: "Raków", 473: "Ind. Rivadavia", 1599: "Philadelphia", 2286: "Pumas",
  348: "Pogoń", 563: "Beer Sheva", 438: "Vélez", 1595: "Seattle", 456: "Talleres",
  604: "Maccabi TA", 565: "Young Boys", 632: "U Craiova", 440: "Belgrano", 608: "Hajduk Split",
  478: "Instituto", 733: "Standard", 1604: "NYCFC", 442: "Defensa", 476: "Riestra",
  1596: "San Jose", 782: "Liberec", 1123: "Aris", 185: "Paderborn", 20787: "St. Louis",
  1612: "Minnesota", 4686: "Stockport", 602: "Apollon", 4665: "Racing", 5902: "La Louvière",
  3723: "Hradec", 1079: "Krylia", 350: "Cracovia", 1598: "Orlando", 2432: "Barracas",
  426: "Sparta R'dam", 635: "Dinamo Buc.", 410: "Go Ahead", 1600: "Houston", 2391: "Puskás",
  544: "Deportivo", 455: "Atl. Tucumán", 2314: "San Luis", 1605: "LA Galaxy", 1606: "Salt Lake",
  6813: "Makhachkala", 1065: "Central Córdoba", 1610: "Colorado", 457: "Newell's",
  474: "Sarmiento", 1617: "Portland", 2290: "Querétaro", 333: "Sarpsborg", 345: "Zagłębie",
  657: "Beitar",
};
// Each club is one line (name, flag, league), so every row is the same height. Where the name
// would be cut short, drop the league and keep just the flag; where it still would be, use the
// club's short name if it has one; past that it ends in "…" (the full name on hover). Each pass
// does its changes first and then its measuring, so the layout is worked out once a pass.
function fitClubMeta(wrap) {
  const names = [...wrap.querySelectorAll("table.clubs .club-cell > .team-link")];
  for (const a of names) {
    a.parentElement.classList.remove("flag-only");
    if (a.dataset.full) { a.textContent = a.dataset.full; delete a.dataset.full; }
    a.removeAttribute("title");
  }
  const cutShort = (a) => a.scrollWidth > a.clientWidth;
  const cut = names.filter(cutShort);
  for (const a of cut) a.parentElement.classList.add("flag-only");
  const still = cut.filter(cutShort);
  for (const a of still) {
    const full = a.textContent, short = CLUB_SHORT[a.closest("tr")?.dataset.team];
    if (short) { a.dataset.full = full; a.textContent = short; }
    a.title = full;
  }
}
// ...and again whenever the table's width changes, not only the window's (a scrollbar appearing
// once the rows are in, the side menu, a split-screen pane)
const clubTableWidths = new WeakMap();
const clubTableObserver = new ResizeObserver((entries) => {
  for (const e of entries) {
    const w = Math.round(e.contentRect.width);
    if (clubTableWidths.get(e.target) === w) continue;          // only its height changed
    clubTableWidths.set(e.target, w);
    fitClubMeta(e.target);
  }
});
const teamName = (id) => state.data.teams[id] || state.players?.teams?.[id] || `Team ${id}`;
// No club badges, competition logos or player and coach photos: badges and logos are the clubs' and
// competitions' trade marks and the photos belong to photographers. Each is a chip instead, the
// initials on a colour of the club's or competition's own (worked out from its id, so the same
// everywhere; not its kit colours) or, for a person, on the plain chip colour. The only third-party
// images left are flagcdn's flags (public domain); a broken one is hidden by the error listener below
const CREST_SKIP = new Set(["fc", "afc", "cf", "sc", "ac", "as", "cd", "ud", "sd", "rc", "fk", "sk", "nk", "bk", "sv",
  "if", "de", "del", "la", "le", "el", "the", "and", "of", "&"]);
function crestInitials(name, skip) {
  const all = String(name || "").replace(/[.'’]/g, "").split(/[\s-]+/).filter(Boolean);
  const kept = skip ? all.filter((w) => !CREST_SKIP.has(w.toLowerCase())) : all;
  const words = kept.length ? kept : all;
  if (!words.length) return "?";
  return (words.length === 1 ? [...words[0]].slice(0, 3).join("") : words.slice(0, 3).map((w) => [...w][0]).join("")).toUpperCase();
}
// his first and last initials: "E. Haaland" -> "EH", "Rodri" -> "R"
function personInitials(name) {
  const w = String(name || "").replace(/\./g, " ").split(/\s+/).filter(Boolean);
  return w.length ? ([...w[0]][0] + (w.length > 1 ? [...w[w.length - 1]][0] : "")).toUpperCase() : "?";
}
const crestHue = (id) => Math.round((Number(id) || 0) * 137.508 % 360);
// cls sizes it (club-logo, club-logo-lg, next5-comp ...); attrs adds data-club / data-league (which
// make it open that page) or a title; a label is read out, otherwise it's hidden from screen readers
const chip = (text, cls, attrs, label, style = "") => `<span class="${cls}"${style} ${attrs}${label ? ` role="img" aria-label="${escapeHtml(label)}"` : ` aria-hidden="true"`}><b>${escapeHtml(text)}</b></span>`;
const clubCrest = (id, cls = "club-logo", attrs = "", label = "", name = teamName(id)) =>
  chip(crestInitials(name, true), `${cls} crest`, attrs, label, ` style="--crest-h:${crestHue(id)}"`);
const leagueCrest = (lid, cls = "club-logo", attrs = "", label = "") =>
  chip(crestInitials(SHORT_NAMES[lid] || state.data.competitions[lid]?.name || compLabel(lid), false), `${cls} crest`, attrs, label, ` style="--crest-h:${crestHue(Number(lid) + 7)}"`);
const personChip = (name, cls = "player-photo") => chip(personInitials(name), `${cls} person-chip`, "", "");
const clubHref = (id) => `#/club/${id}`;
const clubLink = (id, text = teamName(id)) => `<a class="team-link" href="${clubHref(id)}">${escapeHtml(text)}</a>`;
// a player's club, or a note when he has left his last club and his new one isn't known
const playerClub = (p) => p.team ? clubLink(p.team) : `<span class="dim-text">club not known</span>`;
const playerLink = (id, text) => `<a class="player-link" href="#/player/${id}">${escapeHtml(text)}</a>`;
// His surname, for narrow tables: "E. Haaland" -> "Haaland", "Lamine Yamal" -> "Yamal", "V. van Dijk"
// -> "van Dijk", "Vinícius Júnior" -> "Vinícius Jr.", "Son Heung-Min" (surname first) -> "Son"
const NAME_PARTICLES = new Set(["van", "von", "de", "den", "der", "da", "das", "do", "dos", "di", "del", "della", "du",
  "le", "la", "lo", "el", "al", "ben", "ter", "ten", "mac", "st.", "bin", "abu"]);
const NAME_SUFFIXES = new Set(["júnior", "junior", "jr", "jr."]);     // not Neto or Filho: surnames too (Pedro Neto)
function shortName(name) {
  const initials = /^(\p{Lu}\.\s*)+/u.exec(name);
  if (initials) return name.slice(initials[0].length) || name;
  const w = name.split(/\s+/);
  if (w.length < 2) return name;
  if (w.length === 2 && /^\p{Lu}\p{Ll}+-\p{Lu}\p{Ll}+$/u.test(w[1])) return w[0];     // Korean: family name first
  if (NAME_SUFFIXES.has(w[w.length - 1].toLowerCase())) return `${w[0]} Jr.`;
  let i = w.length - 1;
  while (i > 1 && NAME_PARTICLES.has(w[i - 1].toLowerCase())) i--;
  return w.slice(i).join(" ");
}
// Flag for a nationality (API-Football's country names -> ISO codes; flagcdn has the home nations too)
const FLAG_CODES = Object.assign(Object.create(null), {"Afghanistan": "af", "Albania": "al", "Andorra": "ad", "Bosnia": "ba", "Gibraltar": "gi", "Algeria": "dz", "Angola": "ao", "Antigua and Barbuda": "ag", "Argentina": "ar", "Armenia": "am", "Australia": "au", "Austria": "at", "Azerbaijan": "az", "Barbados": "bb", "Belgium": "be", "Benin": "bj", "Bermuda": "bm", "Bolivia": "bo", "Bosnia and Herzegovina": "ba", "Brazil": "br", "Bulgaria": "bg", "Burkina Faso": "bf", "Burundi": "bi", "Cameroon": "cm", "Canada": "ca", "Cape Verde": "cv", "Central African Republic": "cf", "Chad": "td", "Chile": "cl", "Colombia": "co", "Comoros": "km", "Congo": "cg", "Congo DR": "cd", "Costa Rica": "cr", "Croatia": "hr", "Cuba": "cu", "Curaçao": "cw", "Cyprus": "cy", "Czech Republic": "cz", "Czechia": "cz", "Côte d'Ivoire": "ci", "Denmark": "dk", "Dominican Republic": "do", "Ecuador": "ec", "Egypt": "eg", "El Salvador": "sv", "England": "gb-eng", "Equatorial Guinea": "gq", "Estonia": "ee", "Faroe Islands": "fo", "Finland": "fi", "France": "fr", "French Guiana": "gf", "Gabon": "ga", "Gambia": "gm", "Georgia": "ge", "Germany": "de", "Ghana": "gh", "Great Britain": "gb", "Greece": "gr", "Grenada": "gd", "Guadeloupe": "gp", "Guatemala": "gt", "Guinea": "gn", "Guinea-Bissau": "gw", "Guyana": "gy", "Haiti": "ht", "Honduras": "hn", "Hungary": "hu", "Iceland": "is", "Indonesia": "id", "Iran": "ir", "Iraq": "iq", "Israel": "il", "Italy": "it", "Ivory Coast": "ci", "Jamaica": "jm", "Japan": "jp", "Jordan": "jo", "Kazakhstan": "kz", "Kenya": "ke", "Korea Republic": "kr", "Kosovo": "xk", "Latvia": "lv", "Lebanon": "lb", "Liberia": "lr", "Libya": "ly", "Lithuania": "lt", "Luxembourg": "lu", "Madagascar": "mg", "Malawi": "mw", "Mali": "ml", "Malta": "mt", "Mexico": "mx", "Montenegro": "me", "Montserrat": "ms", "Morocco": "ma", "Mozambique": "mz", "Namibia": "na", "Netherlands": "nl", "New Zealand": "nz", "Niger": "ne", "Nigeria": "ng", "North Macedonia": "mk", "Northern Ireland": "gb-nir", "Norway": "no", "Panama": "pa", "Paraguay": "py", "Peru": "pe", "Poland": "pl", "Portugal": "pt", "Republic of Ireland": "ie", "Romania": "ro", "Russia": "ru", "Rwanda": "rw", "Saudi Arabia": "sa", "Scotland": "gb-sct", "Senegal": "sn", "Serbia": "rs", "Sierra Leone": "sl", "Slovakia": "sk", "Slovenia": "si", "South Africa": "za", "Spain": "es", "Sri Lanka": "lk", "St. Kitts and Nevis": "kn", "St. Lucia": "lc", "Suriname": "sr", "Sweden": "se", "Switzerland": "ch", "Tanzania": "tz", "Thailand": "th", "Togo": "tg", "Trinidad and Tobago": "tt", "Tunisia": "tn", "Turkey": "tr", "Türkiye": "tr", "USA": "us", "Uganda": "ug", "Ukraine": "ua", "Uruguay": "uy", "Uzbekistan": "uz", "Venezuela": "ve", "Wales": "gb-wls", "Zambia": "zm", "Zimbabwe": "zw"});
const flagImg = (nat) => FLAG_CODES[nat] ? `<img class="flag" src="https://flagcdn.com/w40/${FLAG_CODES[nat]}.png" alt="" loading="lazy" data-broken="remove">` : "";
// country and competition pages
const countryDisplay = (c) => c === "World" ? "International" : (c || "").replace(/-/g, " ");
const countryHref = (c) => `#/country/${encodeURIComponent(c)}`;
const leagueHref = (lid) => `#/league/${lid}`;
// Every club and competition chip opens its page: tagged data-club / data-league, one listener for
// the whole site (not links of their own, so a chip inside a clickable row or card works too; ones
// inside a link or button keep that control's behaviour)
document.addEventListener("click", (e) => {
  const crest = e.target.closest(".crest[data-club], .crest[data-league]");
  if (!crest || crest.closest("a, button")) return;
  e.preventDefault();
  e.stopPropagation();
  location.hash = crest.dataset.club ? clubHref(crest.dataset.club) : leagueHref(crest.dataset.league);
}, true);
// A broken image is hidden (keeping its space), or removed where tagged data-broken="remove". One
// capturing listener instead of inline onerror attributes, so the Content-Security-Policy in
// index.html can refuse all inline script
document.addEventListener("error", (e) => {
  const img = e.target;
  if (img.tagName !== "IMG") return;
  if (img.dataset.broken === "remove") img.remove(); else img.style.visibility = "hidden";
}, true);
const countryLink = (c) => `<a class="nat-link" href="${countryHref(c)}">${escapeHtml(countryDisplay(c))}</a>`;
const leagueLink = (lid) => `<a class="nat-link" href="${leagueHref(lid)}">${escapeHtml(SHORT_NAMES[lid] || state.data.competitions[lid]?.name || compLabel(lid))}</a>`;
// His flag, linking to the national team's page (the country's name where there's no flag)
const playerFlag = (nat) => !nat ? "" : FLAG_CODES[nat]
  ? `<a class="pl-flag" href="#/nation/${encodeURIComponent(nat)}" title="${escapeHtml(nat)}" aria-label="${escapeHtml(nat)} national team">${flagImg(nat)}</a>`
  : natLink(nat);
// the country as its flag, linking to its page (the name where there's no flag, e.g. International)
function flagLink(c) {
  const name = countryDisplay(c);
  return FLAG_CODES[name] ? `<a class="flag-link" href="${countryHref(c)}" title="${escapeHtml(name)}" aria-label="${escapeHtml(name)}">`
    + `<img class="flag" src="https://flagcdn.com/w40/${FLAG_CODES[name]}.png" alt="" loading="lazy"></a>` : `${countryLink(c)} ·`;
}
const natLink = (nat) => nat ? `<a class="nat-link" href="#/nation/${encodeURIComponent(nat)}">${escapeHtml(nat)}</a>` : "";

// The Matches tab leaves out postponed games (they come back under their new date once rescheduled)
const matchesTab = () => state.matchesTab ||= state.data.matches.filter((m) => m.status !== "PST");
// Today if anything is on, otherwise the nearest upcoming day with matches
function defaultDate() {
  const today = localDateStr(new Date());
  const days = [...new Set(matchesTab().map((m) => localDateStr(new Date(m.kickoff))))].sort();
  if (days.includes(today)) return today;
  return days.find((d) => d > today) || days[days.length - 1] || today;
}

// ------------------------------------------------------------------ filter chips
// ---- Rankings country / league filter
const COUNTRY_FIRST = ["England", "Germany", "Spain", "Italy", "France"];
// Every other country goes under a region; anything not listed here is "Rest of Europe"
// (UEFA members such as Turkey, Israel and Kazakhstan included).
const REGIONS = ["Rest of Europe", "Western Europe", "Eastern Europe", "Scandinavia", "Balkans", "Baltics", "South America", "Africa", "Oceania", "Asia", "North America"];
const REGION_OF = {};
for (const [region, list] of Object.entries({
  "Western Europe": ["Portugal", "Netherlands", "Belgium", "Scotland", "Switzerland", "Austria", "Andorra", "Gibraltar",
    "Ireland", "Northern Ireland", "Wales", "Luxembourg", "Malta"],
  "Eastern Europe": ["Czech Republic", "Hungary", "Poland", "Russia", "Slovakia", "Ukraine", "Belarus", "Moldova"],
  "Scandinavia": ["Denmark", "Norway", "Sweden", "Finland", "Iceland"],
  "Balkans": ["Albania", "Bosnia", "Bulgaria", "Croatia", "Greece", "Kosovo", "Montenegro", "North Macedonia", "Romania", "Serbia", "Slovenia"],
  "Baltics": ["Estonia", "Latvia", "Lithuania"],
  "South America": ["Argentina", "Brazil", "Chile", "Colombia", "Uruguay", "Paraguay", "Peru", "Ecuador", "Bolivia", "Venezuela"],
  "Africa": ["Egypt", "Morocco", "South Africa", "Nigeria", "Tunisia", "Algeria", "Ghana", "Senegal", "Ivory Coast", "Cameroon", "Kenya", "Tanzania", "Zambia"],
  "Oceania": ["Australia", "New Zealand", "Fiji"],
  "Asia": ["Saudi Arabia", "Japan", "South Korea", "China", "Qatar", "United Arab Emirates", "Iran", "Iraq", "India", "Thailand", "Vietnam", "Indonesia", "Malaysia", "Uzbekistan", "Kuwait", "Bahrain", "Oman", "Jordan"],
  "North America": ["USA", "Mexico", "Canada", "Costa Rica", "Honduras", "Guatemala", "Jamaica", "Panama", "El Salvador"],
})) for (const c of list) REGION_OF[c] = region;
const regionOf = (country) => REGION_OF[country] || "Rest of Europe";

function tableCountries() {
  const present = new Set(state.rankings.map((r) => String(r.league)));
  const byCountry = new Map();
  for (const [id, c] of Object.entries(state.data.competitions)) {
    if (c.type !== "League" || c.country === "World" || !present.has(id)) continue;
    const name = c.country.replace(/-/g, " ");
    if (!byCountry.has(name)) byCountry.set(name, []);
    byCountry.get(name).push(Number(id));
  }
  const rank = (n) => { const i = COUNTRY_FIRST.indexOf(n); return i === -1 ? 99 : i; };
  return [...byCountry.entries()]
    .map(([name, ids]) => ({ name, leagues: ids.sort((a, b) => a - b), region: COUNTRY_FIRST.includes(name) ? null : regionOf(name) }))
    .sort((a, b) => rank(a.name) - rank(b.name) || a.name.localeCompare(b.name));
}
// ---- Cups on the Rankings menu, from each competition's league file. European cups ("e:"):
// the clubs in the league phase. Domestic cups ("k:"): the clubs still in.
const EURO_CUPS = [2, 3, 848];
const DOMESTIC_CUPS = [45, 48, 46, 47, 181, 185];
const CUP_DONE = new Set(["FT", "AET", "PEN", "AWD", "WO"]);
// Clubs still in a knockout cup: everyone drawn so far, less the losers of settled ties. A tie is
// every leg between the same two clubs in a round: aggregate, then the shoot-out where its score
// is known. A level tie (a replay to come) or a shoot-out without a score is settled by which
// club turns up later against someone else. Group matches knock nobody out; once knockout ties
// follow the group stage, the group clubs not in them are out. Clubs yet to enter (the Premier
// League in the FA Cup, say) aren't in the file, so aren't counted.
function cupTeamsLeft(lg) {
  const fx = rowsToObjects(lg.fixture_fields, lg.fixtures).filter((f) => !OFF.has(f.status));
  const isGroup = (f) => /group/i.test(f.round || "");
  const out = new Set();
  const groupFx = fx.filter(isGroup), koFx = fx.filter((f) => !isGroup(f));
  if (groupFx.length) {
    const groupEnd = groupFx.reduce((m, f) => f.kickoff > m ? f.kickoff : m, "");
    const after = koFx.filter((f) => f.kickoff > groupEnd);
    if (after.length) {
      const through = new Set(after.flatMap((f) => [f.home, f.away]));
      for (const f of groupFx) for (const t of [f.home, f.away]) if (!through.has(t)) out.add(t);
    }
  }
  const ties = new Map();
  for (const f of koFx) {
    const key = `${f.round}|${Math.min(f.home, f.away)}|${Math.max(f.home, f.away)}`;
    if (!ties.has(key)) ties.set(key, []);
    ties.get(key).push(f);
  }
  const playsLater = (t, opp, after) => koFx.some((f) => f.kickoff > after && (f.home === t || f.away === t) && f.home !== opp && f.away !== opp);
  for (const legs of ties.values()) {
    if (!legs.every((f) => CUP_DONE.has(f.status) && f.hg != null)) continue;
    const a = legs[0].home, b = legs[0].away, last = legs[legs.length - 1];
    const goals = (t) => legs.reduce((n, f) => n + (f.home === t ? f.hg : f.ag), 0);
    let loser = goals(a) > goals(b) ? b : goals(b) > goals(a) ? a : null;
    if (loser == null && last.pen_h != null && last.pen_a != null && last.pen_h !== last.pen_a)
      loser = last.pen_h > last.pen_a ? last.away : last.home;
    if (loser == null) {
      const aOn = playsLater(a, b, last.kickoff), bOn = playsLater(b, a, last.kickoff);
      if (aOn !== bOn) loser = aOn ? b : a;
    }
    if (loser != null) out.add(loser);
  }
  return new Set(fx.flatMap((f) => [f.home, f.away]).filter((t) => !out.has(t)));
}
function loadEuroCups() {
  if (state.euroLoading) return state.euroLoading;
  const ids = [...EURO_CUPS, ...DOMESTIC_CUPS];
  // through loadLeague, so a cup's page opened later reuses the file
  state.euroLoading = Promise.all(ids.map(loadLeague))
    .then((files) => {
      state.euro = new Map(ids.map((lid, i) => {
        const lg = files[i];
        if (!lg) return [lid, new Set()];
        if (DOMESTIC_CUPS.includes(lid)) return [lid, cupTeamsLeft(lg)];
        // the league phase once it has a table; before that everyone drawn in the competition
        const teams = lg.table.length ? lg.table.map((r) => r[2]) : lg.fixtures.flatMap((f) => [f[3], f[4]]);
        return [lid, new Set(teams)];
      }));
      if (state.rankings) { renderTableFilters(); if (isCupFilter(state.tableFilter)) renderTable(); }
    });
  return state.euroLoading;
}
const isCupFilter = (f) => f.startsWith("e:") || f.startsWith("k:");
// the clubs for a cup filter ("e:all" / "k:all" = every cup in the group), or null while loading
function euroTeams(f) {
  if (!state.euro) return null;
  const group = f === "e:all" ? EURO_CUPS : f === "k:all" ? DOMESTIC_CUPS : null;
  if (group) return new Set(group.flatMap((lid) => [...state.euro.get(lid)]));
  return state.euro.get(Number(f.slice(2))) || new Set();
}
// League ids for the current filter: null = all (a European cup filter picks clubs, not leagues)
function tableLeagueIds() {
  const f = state.tableFilter;
  if (f === "all" || isCupFilter(f)) return null;
  if (f.startsWith("c:")) return tableCountries().find((c) => c.name === f.slice(2))?.leagues || [];
  if (f.startsWith("r:")) return tableCountries().filter((c) => c.region === f.slice(2)).flatMap((c) => c.leagues);
  return [Number(f)];
}
function tableFilterIsWide() {   // spans several leagues: show league names and use the scroll box
  const ids = tableLeagueIds();
  return ids === null || ids.length > 1;
}
// ---- Exclude: the big five countries and whole continents hidden from the Rankings (Clubs
// and Players), on top of the competition menu, so "All" less the big five, or the Champions
// League less England. A search ignores it, as it does the menu. Keys: a big-five country's
// name, or "r:" + a continent (Europe takes in the big five too).
const CONTINENTS = ["Europe", "Africa", "Asia", "Oceania", "South America", "North America"];
// chip labels: "N. America", "S. America" (the full name stays in the key, links and hover text)
const regionLabel = (r) => r.replace(/^(North|South) America$/, (m, d) => `${d[0]}. America`);
const continentOf = (country) => {
  const region = COUNTRY_FIRST.includes(country) ? "Europe" : regionOf(country);
  return CONTINENTS.includes(region) ? region : "Europe";      // the European regions
};
const isExcludeKey = (k) => COUNTRY_FIRST.includes(k) || (k.startsWith("r:") && CONTINENTS.includes(k.slice(2)));
function isExcluded(lid) {
  const ex = state.excluded;
  if (!ex.size || lid == null) return false;
  const c = state.data.competitions[lid]?.country?.replace(/-/g, " ");
  if (!c || c === "World") return false;
  return ex.has(c) || ex.has(`r:${continentOf(c)}`);
}
function renderExcludeFilter() {
  const box = $("#exclude-filter");
  box.hidden = !state.rankings || (state.tableView === "players" && !state.players);
  if (box.hidden) return;
  const ex = state.excluded;
  const chip = (attr, on, label, title) =>
    `<button type="button" class="filter-chip ex-chip" ${attr} aria-pressed="${on}" title="${escapeHtml(title)}">${escapeHtml(label)}</button>`;
  box.innerHTML = `<div class="pos-head"><span>Exclude</span>
      <button type="button" class="pos-clear" data-ex-clear${ex.size ? "" : " hidden"}>Clear</button></div>
    <div class="ex-chips">
      ${chip("data-ex-big5", COUNTRY_FIRST.every((c) => ex.has(c)), "Big 5", `Exclude ${COUNTRY_FIRST.join(", ")}`)}
      ${COUNTRY_FIRST.map((c) => chip(`data-ex="${escapeHtml(c)}"`, ex.has(c), c, `Exclude ${c}'s clubs`)).join("")}
      <span class="ex-break"></span>
      ${CONTINENTS.map((r) => chip(`data-ex="r:${escapeHtml(r)}"`, ex.has(`r:${r}`), regionLabel(r),
        `Exclude every club in ${r}${r === "Europe" ? " (the big five included)" : ""}`)).join("")}
    </div>`;
}
$("#exclude-filter").addEventListener("click", (e) => {
  const ex = state.excluded;
  const b = e.target.closest("[data-ex], [data-ex-big5], [data-ex-clear]");
  if (!b) return;
  if (b.hasAttribute("data-ex-clear")) ex.clear();
  else if (b.hasAttribute("data-ex-big5")) {
    const all = COUNTRY_FIRST.every((c) => ex.has(c));
    for (const c of COUNTRY_FIRST) all ? ex.delete(c) : ex.add(c);
  } else ex.has(b.dataset.ex) ? ex.delete(b.dataset.ex) : ex.add(b.dataset.ex);
  renderExcludeFilter();
  renderTable();
  renderTableFilters();
});
function renderTableFilters() {
  const countries = tableCountries();
  // Clubs (current league members) or ranked players per filter, shown on the right in the side menu
  const counts = new Map();
  let total = 0;
  const players = state.tableView === "players" && state.players;
  for (const r of players ? state.players.list : state.rankings)
    if ((players ? playerVisible(r) : r.in_league) && !isExcluded(r.league)) { counts.set(r.league, (counts.get(r.league) || 0) + 1); total++; }
  const sum = (ids) => ids.reduce((n, id) => n + (counts.get(id) || 0), 0);
  const euroCount = (value) => {
    const teams = euroTeams(value);
    if (!teams) return 0;
    return players ? state.players.list.filter((p) => teams.has(p.team) && playerVisible(p) && !isExcluded(p.league)).length
      : state.rankings.filter((r) => teams.has(r.team) && !isExcluded(r.league)).length;
  };
  const countOf = (value) => value === "all" ? total
    : isCupFilter(value) ? euroCount(value)
    : value.startsWith("c:") ? sum(countries.find((c) => c.name === value.slice(2))?.leagues || [])
    : value.startsWith("r:") ? sum(countries.filter((c) => c.region === value.slice(2)).flatMap((c) => c.leagues))
    : counts.get(Number(value)) || 0;
  renderFilterMenu($("#table-filters"), state.tableFilter, countries, countOf, {
    all: "All leagues", country: (c) => `All ${c} clubs`, region: (r) => `All clubs in ${r}`,
    euro: "Clubs in this season's Champions League, Europa League or Conference League",
    cup: (name) => `Clubs in the ${name} league phase`,
    domestic: "Clubs still in a domestic cup (clubs yet to enter aren't counted)",
    domesticCup: (name) => `Clubs still in the ${name} (clubs yet to enter aren't counted)`,
  });
  renderMoreFilters();
}
// The country / league menu on Clubs, Matches, Stats and Bets: All, European cups, the big five
// countries, then the rest by region. countries = [{ name, leagues, region }]; countOf(value) =
// the number shown beside each filter (null: no numbers, nothing greyed out); titles = hover text.
// Wide screens: a side menu. Narrower: the same menu behind a button naming the selection.
function renderFilterMenu(wrap, f, countries, countOf, titles) {
  const leagueName = (id) => SHORT_NAMES[id] || state.data.competitions[id].name;
  const names = Object.create(null); // each filter's name, for the button
  const chip = (value, label, title, extra = "", cls = "", full = label) => (names[value] = full,
    `<button type="button" class="filter-chip ${cls}${!countOf || countOf(value) ? "" : " none"}" data-filter="${escapeHtml(value)}" title="${escapeHtml(title)}" aria-pressed="${f === value}">${extra}<span class="flabel">${label}</span>${countOf ? `<span class="cnt">${countOf(value)}</span>` : ""}</button>`);
  const caret = `<span class="caret" aria-hidden="true">▾</span>`;
  const list = (html) => `<div class="league-list"><div class="ll-inner">${html}</div></div>`;
  const activeCountry = f.startsWith("c:") ? countries.find((c) => c.name === f.slice(2))
    : countries.find((c) => c.leagues.includes(Number(f)));
  const activeRegion = f.startsWith("r:") ? f.slice(2) : activeCountry?.region;

  // A country: one league = a plain chip; several = a chip that opens its leagues
  const countryGroup = (c) => {
    if (c.leagues.length === 1) return chip(String(c.leagues[0]), escapeHtml(c.name), `${c.name} · ${leagueName(c.leagues[0])}`);
    const inside = c.leagues.includes(Number(f));
    return `<div class="cgroup${activeCountry === c ? " open" : ""}">${chip(`c:${c.name}`, escapeHtml(c.name), titles.country(c.name), caret, `cchip${inside ? " has-active" : ""}`)}${list(c.leagues.map((id) => chip(String(id), escapeHtml(leagueName(id)), leagueName(id), "", "", `${escapeHtml(c.name)} · ${escapeHtml(leagueName(id))}`)).join(""))}</div>`;
  };
  const regionGroups = REGIONS.map((region) => {
    const members = countries.filter((c) => c.region === region);
    if (!members.length) return "";
    const inside = activeRegion === region && f !== `r:${region}`;
    return `<div class="cgroup region${activeRegion === region ? " open" : ""}">${chip(`r:${region}`, escapeHtml(regionLabel(region)), titles.region(region), caret, `cchip${inside ? " has-active" : ""}`)}${list(members.map(countryGroup).join(""))}</div>`;
  });

  const euroGroup = `<div class="cgroup${f.startsWith("e:") ? " open" : ""}">${chip("e:all", "European cups", titles.euro, caret,
    `cchip${f.startsWith("e:") && f !== "e:all" ? " has-active" : ""}`)}${list(EURO_CUPS.map((lid) =>
      chip(`e:${lid}`, escapeHtml(leagueName(lid)), titles.cup(leagueName(lid)))).join(""))}</div>`;
  const cupsGroup = titles.domestic ? `<div class="cgroup${f.startsWith("k:") ? " open" : ""}">${chip("k:all", "Domestic cups", titles.domestic, caret,
    `cchip${f.startsWith("k:") && f !== "k:all" ? " has-active" : ""}`)}${list(DOMESTIC_CUPS.map((lid) =>
      chip(`k:${lid}`, escapeHtml(leagueName(lid)), titles.domesticCup(leagueName(lid)))).join(""))}</div>` : "";
  const intl = titles.intl ? intlLeagues() : [];
  const intlGroup = intl.length ? `<div class="cgroup${f.startsWith("i:") ? " open" : ""}">${chip("i:all", "Internationals", titles.intl, caret,
    `cchip${f.startsWith("i:") && f !== "i:all" ? " has-active" : ""}`)}${list(intl.map((lid) =>
      chip(`i:${lid}`, escapeHtml(leagueName(lid)), titles.cup(leagueName(lid)))).join(""))}</div>` : "";
  const menu = `${chip("all", "All", titles.all)}
      ${euroGroup}
      ${intlGroup}
      ${cupsGroup}
      <div class="sep"></div>
      ${countries.filter((c) => !c.region).map(countryGroup).join("")}
      <div class="sep"></div>
      ${regionGroups.join("")}`;
  const open = wrap.classList.contains("menu-open"), n = countOf ? countOf(f) : null;
  const scrolled = wrap.querySelector(".cgroups")?.scrollTop || 0;
  wrap.innerHTML = `<button type="button" class="menu-trigger" aria-expanded="${open}">
      <span class="mt-name">${names[f] ?? "All"}</span>${n != null ? `<span class="cnt">${n}</span>` : ""}<span class="caret" aria-hidden="true">▾</span></button>
    <div class="cgroups">${menu}</div>`;
  wrap.querySelector(".cgroups").scrollTop = scrolled;     // a group opened: the list stays put
  bindFilterHover(wrap);
}
// Narrower screens: the button opens and closes its menu. Picking a group (a region, a country
// with several leagues, a set of cups) opens it, and the menu stays open to go further in;
// picking anything else, or tapping outside, closes it. Capture phase: this runs before the
// menu's own click handler rebuilds it.
const closeFilterMenus = (except) => document.querySelectorAll(".side-filters.menu-open").forEach((w) => {
  if (w === except) return;
  w.classList.remove("menu-open");
  w.querySelector(".menu-trigger")?.setAttribute("aria-expanded", "false");
});
document.addEventListener("click", (e) => {
  const trigger = e.target.closest(".menu-trigger");
  if (trigger) {
    const wrap = trigger.closest(".side-filters"), open = !wrap.classList.contains("menu-open");
    closeFilterMenus(wrap);
    if (open && $("#table-side").classList.contains("filters-open")) {   // one panel at a time
      $("#table-side").classList.remove("filters-open");
      renderMoreFilters();
    }
    wrap.classList.toggle("menu-open", open);
    trigger.setAttribute("aria-expanded", String(open));
    // open on the selection, a third of the way down, with its group's list under it
    const list = wrap.querySelector(".cgroups"), on = list.querySelector('[aria-pressed="true"]');
    if (open && on) list.scrollTop = on.getBoundingClientRect().top - list.getBoundingClientRect().top - list.clientHeight / 3;
    return;
  }
  const pick = e.target.closest(".side-filters [data-filter]");
  if (pick) { if (!pick.classList.contains("cchip")) closeFilterMenus(); return; }
  if (!e.target.closest(".side-filters")) closeFilterMenus();
}, true);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeFilterMenus(); });

// ---- Matches, Stats and Bets: the same menu over the competitions each has (cups under their
// country, the European cups in their own group); no counts, nothing greyed out
function compCountries(ids) {
  const comps = state.data.competitions;
  const present = new Set([...ids].map(Number).filter((id) => comps[id]));
  const byCountry = new Map();
  for (const id of present) {
    const c = comps[id];
    if (!c || c.country === "World") continue;
    const name = c.country.replace(/-/g, " ");
    if (!byCountry.has(name)) byCountry.set(name, []);
    byCountry.get(name).push(id);
  }
  const rank = (n) => { const i = COUNTRY_FIRST.indexOf(n); return i === -1 ? 99 : i; };
  const orderOf = (id) => { const i = GROUP_ORDER.indexOf(id); return i === -1 ? 999 : i; };
  // leagues before cups, then the Matches tab's usual order
  const byOrder = (a, b) => (comps[a].type !== "League") - (comps[b].type !== "League") || orderOf(a) - orderOf(b) || a - b;
  return [...byCountry.entries()]
    .map(([name, ids]) => ({ name, leagues: ids.sort(byOrder), region: COUNTRY_FIRST.includes(name) ? null : regionOf(name) }))
    .sort((a, b) => rank(a.name) - rank(b.name) || a.name.localeCompare(b.name));
}
// Competition ids for a menu filter value: null = all
function filterLeagueIds(f, countries) {
  if (f === "all") return null;
  if (f === "e:all") return EURO_CUPS;
  if (f === "k:all") return DOMESTIC_CUPS;
  if (f === "i:all") return intlLeagues();
  if (f.startsWith("e:") || f.startsWith("k:") || f.startsWith("i:")) return [Number(f.slice(2))];
  if (f.startsWith("c:")) return countries.find((c) => c.name === f.slice(2))?.leagues || [];
  if (f.startsWith("r:")) return countries.filter((c) => c.region === f.slice(2)).flatMap((c) => c.leagues);
  return [Number(f)];
}
function matchCountries() {
  return state.matchCountries ||= compCountries(state.data.matches.map((m) => m.league));
}
const matchLeagueIds = (f = state.matchFilter) => filterLeagueIds(f, matchCountries());
// National team competitions on the Matches tab (national_fixtures), most matches first
function intlLeagues() {
  if (state.intlLeagues) return state.intlLeagues;
  const count = new Map();
  for (const m of state.data.matches) if (m.intl) count.set(m.league, (count.get(m.league) || 0) + 1);
  return state.intlLeagues = [...count.keys()].sort((a, b) => count.get(b) - count.get(a) || a - b);
}
// Stats: every competition with stats in any range, so the menu stays put when the range changes
function statsCountries() {
  return state.statsCountries ||= compCountries(Object.values(state.stats?.ranges || {}).flatMap(Object.keys).filter((k) => /^\d+$/.test(k)));
}
function renderStatsFilters() {
  renderFilterMenu($("#stats-filters"), state.statsFilter, statsCountries(), null, {
    all: "All competitions", country: (c) => `All ${c} competitions`, region: (r) => `All competitions in ${r}`,
    euro: "Champions League, Europa League and Conference League", cup: (name) => name,
  });
}
function betCountries() {
  return state.betCountries ||= compCountries((state.bets?.bets || []).map((b) => b.league));
}
// Each kind of bet placed once per match (result, goal line, both teams score): when both runs
// bet it, the night-before bet (placed first) counts
const betKind = (b) => `${b.fixture}|${b.market.startsWith("OU") ? "OU" : b.market}`;
function onePerPick(bets) {
  const early = new Set(bets.filter((b) => b.strategy === "early").map(betKind));
  return bets.filter((b) => b.strategy === "early" || !early.has(betKind(b)));
}
// The badge of the team a bet backs, or both teams' for a draw or goals bet
function betBadges(b) {
  const img = (id) => id ? clubCrest(id, "club-logo", `data-club="${id}"`) : "";
  const ids = b.market === "1X2" && b.selection !== "Draw" ? [b.selection === "Home" ? b.home_id : b.away_id] : [b.home_id, b.away_id];
  return `<span class="tip-badges">${ids.map(img).join("")}</span>`;
}
// Bets on the strategy / market / cautious filters, before the competition menu
function betScope() {
  const bets = state.bets?.bets || [];
  return (state.betStrategy === "all" ? onePerPick(bets) : bets).filter((b) =>
    (state.betStrategy === "all" || b.strategy === state.betStrategy) &&
    (state.betMarket === "all" || b.market === state.betMarket) &&
    (state.betView === "all" || b.cautious));
}
// The menu shows how many settled bets each competition, country and region has on those filters
function renderBetFilters() {
  const countries = betCountries(), scope = betScope().filter((b) => b.result === "win" || b.result === "loss");
  const countOf = (value) => {
    const ids = filterLeagueIds(value, countries);
    return ids ? scope.filter((b) => ids.includes(b.league)).length : scope.length;
  };
  renderFilterMenu($("#bet-filters"), state.betFilter, countries, countOf, {
    all: "All competitions", country: (c) => `All ${c} bets`, region: (r) => `All bets in ${r}`,
    euro: "Champions League, Europa League and Conference League bets", cup: (name) => `${name} bets`,
  });
}
function renderMatchFilters() {
  renderFilterMenu($("#match-filters"), state.matchFilter, matchCountries(), null, {
    all: "All competitions", country: (c) => `All ${c} matches`, region: (r) => `All matches in ${r}`,
    euro: "Champions League, Europa League and Conference League matches", cup: (name) => `${name} matches`,
    intl: "National team matches: World Cup, qualifiers, Nations League, friendlies and others",
  });
}
// Phones: the age, position, club and nationality filters sit behind one button, which
// shows how many are on
function renderMoreFilters() {
  const btn = $("#more-filters");
  const players = state.tableView === "players";
  btn.hidden = !state.rankings || (players && !state.players);
  if (btn.hidden) return;
  const n = rangesOn() + state.excluded.size + (!players ? 0 : (state.ageMin != null || state.ageMax != null ? 1 : 0) + (state.positions?.size || 0)
    + (state.clubs?.size || 0) + (state.nats?.size || 0));
  // Clubs has only Exclude behind it, so the button says so
  btn.innerHTML = `${players ? "Filters" : "Exclude"}${n ? `<span class="n">${n}</span>` : ""}<span class="caret" aria-hidden="true">▾</span>`;
  btn.setAttribute("aria-expanded", String($("#table-side").classList.contains("filters-open")));
}
$("#more-filters").addEventListener("click", () => {
  $("#table-side").classList.toggle("filters-open");
  renderMoreFilters();
  fitTopRows($("#table-wrap"), tableFilterIsWide() || !!state.tableSearch.trim());
});

// Side menu (wide screens): a group opens after a short hover, so sweeping the pointer past
// doesn't make the list jump. Groups above the pointer stay open while it is in the menu
// (closing them would pull the rows up under it); ones below close as another group is
// entered, and all of them shortly after the pointer leaves the menu.
const SIDE_MENU = matchMedia("(min-width: 1160px)");
function bindFilterHover(wrap) {
  if (!matchMedia("(hover: hover)").matches) return;
  const groups = [...wrap.querySelectorAll(".cgroup")];
  for (const g of groups) {
    g.addEventListener("mouseenter", () => {
      for (const o of groups) if (g.compareDocumentPosition(o) & Node.DOCUMENT_POSITION_FOLLOWING) {
        clearTimeout(o._open);
        o.classList.remove("hover-open");
      }
      g._open = setTimeout(() => g.classList.add("hover-open"), 140);
    });
    g.addEventListener("mouseleave", () => clearTimeout(g._open));
  }
  if (wrap._hoverBound) return;
  wrap._hoverBound = true;
  wrap.addEventListener("mouseenter", () => clearTimeout(wrap._close));
  wrap.addEventListener("mouseleave", () => {
    wrap._close = setTimeout(() => wrap.querySelectorAll(".cgroup.hover-open")
      .forEach((g) => g.classList.remove("hover-open")), 220);
  });
}
// Update the selection in place: no rebuild, so nothing flickers. Only the groups holding the
// selection stay open; every other one, hover-opened or not, closes.
function syncFilterMenu(wrap, f) {
  wrap.querySelectorAll("[data-filter]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.filter === f)));
  for (const g of wrap.querySelectorAll(".cgroup")) {
    const head = g.querySelector(":scope > .filter-chip");
    const pressed = g.querySelector('[aria-pressed="true"]');
    clearTimeout(g._open);
    g.classList.toggle("open", !!pressed);
    if (!pressed) g.classList.remove("hover-open");
    head.classList.toggle("has-active", !!pressed && pressed !== head);
  }
}

// ------------------------------------------------------------------ matches
// Average XI rank by line [GK, DEF, MID, FWD] as "GK 70 · DEF 71 · MID 74 · FWD 73"
const linesText = (l) => ["GK", "DEF", "MID", "FWD"].map((k, i) => `${k} ${l[i] == null ? "–" : Math.round(l[i])}`).join(" · ");
const SIDES_NOTE = "Attack and Defence average to Current Strength: 200 points of attack over the other side's defence is about one goal. Home and Away are Current Strength plus or minus the club's own home edge.";

function rankChip(rank, title = "Current Strength (Elo)") {
  return Number.isFinite(rank) ? `<span class="club-score" title="${title}">${Math.round(rank).toLocaleString()}</span>` : "";
}

// Home, draw and away as whole percentages that add up to 100, as the bars show them
function shownProbs(m, key) {
  const h = Math.round(m[`${key}_home`] * 100), d = Math.round(m[`${key}_draw`] * 100);
  return [h, d, 100 - h - d];
}
const PROB_NAMES = {
  p: ["Model", "Model probability: the model's home, draw and away chances"],
  m: ["Market fair", "Market fair probability: the average across bookmakers with their margin removed"],
};
// The win-chance bar: the model's by default, or the market's (key "m", margin removed).
// labelled puts a name to the left, so a model and a market bar line up one above the other.
function probBar(m, key = "p", labelled = false) {
  if (m[`${key}_home`] == null) return "";
  const [h, d, a] = shownProbs(m, key);
  const [label, tip] = PROB_NAMES[key];
  return `
    <div class="match-probs${labelled ? " labelled" : ""}">${labelled ? `<span class="prob-name" title="${tip}">${label}</span>` : ""}
      <div class="prob-bar">
        <span class="prob-home" style="width:${h}%"></span>
        <span class="prob-draw" style="width:${d}%"></span>
        <span class="prob-away" style="width:${a}%"></span>
      </div>
      <div class="prob-labels">
        <span class="prob-home" style="left:0; width:${h}%">${h}%</span>
        <span class="prob-draw" style="left:${h}%; width:${d}%">${d}%</span>
        <span class="prob-away" style="left:${h + d}%; width:${a}%">${a}%</span>
      </div>
    </div>`;
}
// Model minus market fair, in whole points of the shown percentages
function marketDiff(m) {
  const model = shownProbs(m, "p"), market = shownProbs(m, "m");
  return model.map((v, i) => { const x = v - market[i]; return `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x)}`; });
}
const DIFF_TIP = "Model probability minus market fair probability, in percentage points. A difference is a disagreement with the market, not a betting edge or proof of value.";
// Both bars where the market's prices are known, else the model's bar; diff adds the gap line
function probBars(m, diff = true) {
  if (m.m_home == null || m.p_home == null) return probBar(m);
  const d = marketDiff(m).map((x) => `<b>${x}</b>`);
  return probBar(m, "p", true) + probBar(m, "m", true)
    + (diff ? `<div class="market-line" title="${DIFF_TIP}">Difference (model − market) H ${d[0]} · D ${d[1]} · A ${d[2]}</div>` : "");
}

// ---- Why the model says what it says. Everything below formats predictions.explain() output
// from data/explanations.json (loaded when the first match card with key reasons is drawn, or a
// card's model detail is opened); none of it is worked out here.
function loadExplanations() {
  state.explainLoading ||= getJsonOrNull("data/explanations.json")
    .then((j) => { state.explain = j?.matches || {}; state.explainModels = j?.models || {}; fillReasons(); });
  return state.explainLoading;
}
const explainOf = (m) => state.explain?.[String(m.id)] || null;
// Goals to one decimal, never "0.0" for something the model did count
const goalsText = (v) => { const a = Math.abs(v); return a === 0 ? "0" : a < 0.05 ? "<0.1" : a.toFixed(1); };
const signedGoals = (v) => v !== 0 && Math.abs(v) < 0.05 ? "≈0" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${goalsText(v)}`;
const MARGIN_LABELS = {
  strength: ["Strength gap", "Home minus away match strength (the blend of Current and Baseline Strength), 100 points = 1 goal"],
  home_advantage: ["Home advantage", "The same for every club: 0.3 goals"],
  europe_home: ["European tie", "Extra home margin in UEFA club competitions"],
  home_edges: ["Clubs' home/away record", "The home side's own home edge plus the away side's own away weakness, from past results"],
  absences: ["Known absences", "Players listed injured, suspended or doubtful, weighted by their recent minutes"],
  lineups: ["Predicted line-ups", "Predicted XI ratings by line (defence, midfield, attack)"],
};
// One key reason as a phrase and its size; + favours the home side (or, for tendencies, more goals)
function reasonHtml(m, [key, v]) {
  const fav = teamName(v >= 0 ? m.home : m.away), other = teamName(v >= 0 ? m.away : m.home);
  const text = {
    strength: `${fav} rated the stronger side`,
    home_advantage: `Home advantage for ${fav}`,
    europe_home: `Extra home advantage in European ties for ${fav}`,
    home_edges: `Clubs' home/away records lean to ${fav}`,
    absences: `More of ${other}'s regulars listed as missing`,
    lineups: `Predicted line-up rated higher for ${fav}`,
    tendencies: v >= 0 ? "Both sides' games tend to be open" : "Both sides' games tend to be tight",
  }[key];
  if (!text) return "";
  const size = key === "tendencies" ? `${signedGoals(v)} total goals` : `${goalsText(v)} goals`;
  return `<li><span>${escapeHtml(text)}</span><b>${size}</b></li>`;
}
const REASONS_TIP = "The model inputs that moved this projection most, in goals of expected margin (or total goals). They describe how the model arrived at its numbers, not what will decide the match.";
function reasonsHtml(m) {
  const x = explainOf(m);
  if (!x?.reasons?.length) return "";
  return `<div class="why-hd" title="${REASONS_TIP}">Key reasons</div><ul class="why-list">${x.reasons.map((r) => reasonHtml(m, r)).join("")}</ul>`;
}
// Fill the key-reason slots of cards drawn before the file arrived
function fillReasons() {
  document.querySelectorAll(".why[data-why]:empty").forEach((el) => {
    const m = state.data.matches.find((x) => x.id === Number(el.dataset.why));
    if (m) el.innerHTML = reasonsHtml(m);
  });
}
const whenText = (iso) => `${fmtShortDate(iso)} ${fmtTime(iso)}`;
const SOURCE_TEXT = {
  prospective: "captured before kickoff",
  late_observation: "captured after kickoff",
  reconstruction: "reconstructed afterwards from pre-match data",
};
function detailRow(label, value, tip = "") {
  return value == null || value === "" ? "" : `<div class="why-row"${tip ? ` title="${escapeHtml(tip)}"` : ""}><span>${label}</span><b>${value}</b></div>`;
}
const pairText = (h, a, f = (v) => Math.round(v).toLocaleString()) => h == null && a == null ? null
  : `${h == null ? "–" : f(h)} · ${a == null ? "–" : f(a)}`;
function whyDetailHtml(m) {
  const x = explainOf(m);
  const finished = FINISHED.has(m.status) && m.hg != null;
  const sections = [];
  const section = (title, rows, note = "") => { if (rows.trim()) sections.push(`<div class="why-sec"><div class="why-sec-hd">${title}</div>${rows}${note}</div>`); };
  const hName = escapeHtml(teamName(m.home)), aName = escapeHtml(teamName(m.away));
  const teamsRow = `<div class="why-row why-teams"><span></span><b>${hName} · ${aName}</b></div>`;

  if (x) {
    const fb = x.fallback?.some(Boolean)
      ? `<div class="why-note">No rating history yet for ${escapeHtml(x.fallback.map((f, i) => f ? teamName(i ? m.away : m.home) : null).filter(Boolean).join(" or "))}: the competition's starting strength was used.</div>` : "";
    section("Strength", teamsRow
      + detailRow("Current Strength", pairText(...x.current), "Elo rating now, from recent results")
      + detailRow("Baseline Strength", pairText(...x.baseline), "Long-term level (LT ALGO)")
      + detailRow("Used for this match", pairText(...x.match), "A blend of Current and Baseline Strength; matches further away lean more on Baseline"), fb);
    const margin = Object.entries(x.margin).map(([k, v]) => {
      const [label, tip] = MARGIN_LABELS[k] || [k, ""];
      return detailRow(label, signedGoals(v), tip);
    }).join("");
    section("Expected margin <span class=\"why-unit\">goals, + favours home</span>", margin
      + detailRow("Total", signedGoals(x.exp_diff), "The model's expected home minus away goals"));
  }

  const goals = [
    x ? detailRow("Competition average", `${x.league_goals.toFixed(1)} a game`, "Average goals per game in this competition over the last 12 months") : "",
    x?.tendencies != null ? detailRow("Attack/defence tendencies", `${signedGoals(x.tendencies)} total`, "How much both clubs' attacking and defensive styles move the expected total, against level sides") : "",
    m.home_xg != null ? detailRow("Projected total", (m.home_xg + m.away_xg).toFixed(1)) : "",
    m.p_over25 != null ? detailRow("Over 2.5 · both score", `${Math.round(m.p_over25 * 100)}% · ${Math.round(m.p_btts * 100)}%`) : "",
  ].join("");
  section("Goals", goals);

  const missH = x ? x.missing[0] : m.home_missing, missA = x ? x.missing[1] : m.away_missing;
  section("Known absences", detailRow("Missing players", pairText(missH, missA, (v) => v.toFixed(1)),
    "Players listed injured, suspended or doubtful, weighted by their share of recent minutes (1.0 = one ever-present player). – = no injury list"));

  const lines = x?.lines;
  const xi = m.home_xi != null && m.away_xi != null;
  section(`${finished ? "Line-ups" : "Predicted line-ups"}`,
    (xi ? detailRow(`${finished ? "Starting" : "Predicted"} XI rating`, `${Math.round(m.home_xi)} · ${Math.round(m.away_xi)}`, "Average player rank (0–100)") : "")
    + (xi && m.home_recent_xi != null && m.away_recent_xi != null ? detailRow("Last 5 XIs", `${Math.round(m.home_recent_xi)} · ${Math.round(m.away_recent_xi)}`) : "")
    + (lines ? ["DEF", "MID", "FWD"].map((k, j) => detailRow(`Model input, ${k}`, pairText(lines[0][j + 1], lines[1][j + 1]),
      "The predicted XI's average rank in this line, as the model used it")).join("") : ""));

  if (m.m_home != null && m.p_home != null) {
    const [ph, pd, pa] = shownProbs(m, "p"), [mh, md, ma] = shownProbs(m, "m"), d = marketDiff(m);
    section("Model vs market <span class=\"why-unit\">H · D · A</span>",
      detailRow("Model", `${ph} · ${pd} · ${pa}%`)
      + detailRow("Market fair", `${mh} · ${md} · ${ma}%`, "The average across bookmakers with their margin removed")
      + detailRow("Difference", `${d.join(" · ")} pts`, DIFF_TIP),
      `<div class="why-note">A disagreement with the market, not a betting edge.</div>`);
  }

  if (x) {
    const v = state.explainModels?.[x.model];
    const model = v?.name ? `${escapeHtml(v.name)}${v.code ? ` · ${escapeHtml(v.code)}` : ""}` : null;
    section("Data", detailRow("Model inputs", `${escapeHtml(whenText(x.captured_at))}`, `Inputs ${SOURCE_TEXT[x.source] || x.source}`)
      + (x.source !== "prospective" ? detailRow("Captured", escapeHtml(SOURCE_TEXT[x.source] || x.source)) : "")
      + detailRow("Injury list seen", x.injuries_at ? escapeHtml(whenText(x.injuries_at)) : null)
      + detailRow("Odds seen", x.odds_at ? escapeHtml(whenText(x.odds_at)) : null)
      + detailRow("Model version", model, x.model ? `Version id ${x.model.slice(0, 11)}` : ""));
  } else if (m.p_home != null) {
    sections.push(`<div class="why-note">No breakdown for this prediction: its captured model inputs aren't available.</div>`);
  }
  return `${sections.join("")}<div class="why-note">These are the model's inputs and how much each moved its numbers, not a statement of what will decide the match.</div>`;
}

function outcome(h, a) { return h > a ? 0 : h === a ? 1 : 2; }

function scoreCentre(m) {
  const finished = FINISHED.has(m.status) && m.hg != null;
  const live = LIVE.has(m.status) && m.hg != null;
  if (finished || live) {
    const pens = m.pen_h != null ? `<div class="score-sub">pens ${m.pen_h}–${m.pen_a}</div>` : "";
    const tip = m.source === "backfill" ? "Projected score, reconstructed afterwards from pre-match data" : "Projected score, before kickoff";
    const proj = m.home_xg != null ? `<div class="score-sub" title="${tip}">${m.home_xg.toFixed(1)}–${m.away_xg.toFixed(1)}</div>` : "";
    return `<div class="match-score"><div class="score-row"><span class="final-box">${m.hg}</span><span class="vs-text">–</span><span class="final-box">${m.ag}</span></div>${pens}${proj}</div>`;
  }
  if (m.home_xg == null) return `<div class="match-score"><div class="score-row"><span class="vs-text">vs</span></div></div>`;
  return `<div class="match-score">
      <div class="score-row" title="Projected goals (the model's expected goals)"><span class="proj-box">${m.home_xg.toFixed(1)}</span><span class="vs-text">xG</span><span class="proj-box">${m.away_xg.toFixed(1)}</span></div>
      ${m.likely ? `<div class="score-sub" title="The single most likely score; most matches end some other way">Likely ${escapeHtml(m.likely)}</div>` : ""}
    </div>`;
}

function statusTag(m) {
  if (LIVE.has(m.status)) return `<span class="status-tag live">Live</span>`;
  if (m.status === "PST") return `<span class="status-tag">Postponed</span>`;
  if (m.status === "CANC" || m.status === "ABD") return `<span class="status-tag">${m.status === "CANC" ? "Cancelled" : "Abandoned"}</span>`;
  if (FINISHED.has(m.status)) return `<span class="status-tag">${m.status === "FT" ? "FT" : m.status}</span>`;
  return "";
}

// A match row's top: time and round, both clubs with badge and rank, and the score (or the
// projected goals and likely score); right = what goes top right. Shared by Matches and Model vs Market.
function matchHead(m, right = "") {
  const finished = FINISHED.has(m.status) && m.hg != null;
  const meta = escapeHtml(m.meta || fmtTime(m.kickoff));
  const round = !m.meta && m.round ? ` · ${escapeHtml(m.round.replace(/^Regular Season - /, "Round "))}` : "";
  const hRank = finished ? m.home_rank : state.rankByTeam.get(m.home)?.current ?? m.home_rank;
  const aRank = finished ? m.away_rank : state.rankByTeam.get(m.away)?.current ?? m.away_rank;
  const rankTitle = finished ? "Strength going into this match (Elo)" : "Current Strength (Elo)";
  // national teams: the name opens the nation page (no club page to open, no squad badges)
  const side = (id, name, where) => m.intl
    ? `${clubCrest(id, "club-logo")}<a class="team-link" href="#/nation/${encodeURIComponent(state.data.nation_pages?.[id] || teamName(id))}">${escapeHtml(name || teamName(id))}</a>`
    : `${clubCrest(id, "club-logo", `data-club="${id}"`)}${clubLink(id, name)}<span class="team-squad-badges" data-squad-team="${where}"></span>`;
  return `
      <div class="match-card-top">
        <span class="match-meta">${meta}${round}</span>
        <span class="card-top-right">${right}</span>
      </div>
      <div class="match-teams">
        <div class="match-team">
          <div class="mt-name">${side(m.home, m.home_name, "home")}</div>
          <div class="score-badges">${rankChip(hRank, rankTitle)}<span data-squad-overall="home"></span></div>
        </div>
        ${scoreCentre(m)}
        <div class="match-team away">
          <div class="mt-name">${side(m.away, m.away_name, "away")}</div>
          <div class="score-badges"><span data-squad-overall="away"></span>${rankChip(aRank, rankTitle)}</div>
        </div>
      </div>`;
}

// lineups: false leaves out the Line-ups button (club pages)
function matchCard(m, { lineups = true } = {}) {
  const finished = FINISHED.has(m.status) && m.hg != null;
  const rated = finished && m.rating;
  const canLineup = lineups && !m.intl && !LIVE.has(m.status) && !CALLED_OFF.has(m.status);
  const cls = (rated ? ` rated acc-${m.rating}` : "") + (canLineup ? " lineup-card" : "");
  const badge = rated
    ? `<span class="rating-badge badge-${m.rating}" title="${m.rating}/5 ${RATING_LABELS[m.rating]}">${m.rating}/5</span>` : "";
  const detail = rated ? `<div class="rating-detail" hidden>
      <div class="factor"><span class="factor-name">Overall</span><span class="factor-score">${m.rating}/5 ${RATING_LABELS[m.rating]}</span></div>
      ${FACTORS.map(([k, label, w]) => `<div class="factor"><span class="factor-name">${label} <span class="factor-weight">${w}</span></span><span class="factor-score">${m[k]}/5</span></div>`).join("")}
    </div>` : "";
  // Up front: projected goals and likely score (in the head), model and market chances, key
  // reasons; the line-ups and everything else behind "Line-ups" and "Model detail"
  const upcoming = !finished && !LIVE.has(m.status);
  const toggles = (canLineup ? `<button type="button" class="lineup-toggle" aria-expanded="false">${finished ? "Line-ups" : "Predicted line-ups"}</button>` : "")
    + (m.p_home != null ? `<button type="button" class="why-toggle" aria-expanded="false">${finished ? "Pre-match model detail" : "Model detail"}</button>` : "");
  return `
    <div class="match-card${cls}" data-fixture="${m.id}">
      ${matchHead(m, `${badge}${statusTag(m)}`)}
      ${probBars(m, false)}
      ${upcoming && m.p_home != null ? `<div class="why" data-why="${m.id}">${loadExplanations() && reasonsHtml(m)}</div>` : ""}
      ${upcoming && !m.intl ? `<div class="market-line squad-line" data-fixture="${m.id}" hidden></div>` : ""}
      ${toggles ? `<div class="card-toggles">${toggles}</div>` : ""}
      ${m.p_home != null ? `<div class="why-detail" hidden></div>` : ""}
      ${detail}
    </div>`;
}

// ---- Rounds: a single competition is shown a round at a time, not a day at a time
// The competition a filter picks on its own (a league, or one European cup), or null
function matchSingleLeague(f = state.matchFilter) {
  if (/^\d+$/.test(f)) return Number(f);
  if (/^[ei]:\d+$/.test(f)) return Number(f.slice(2));
  return null;
}
const ROUND_WINDOW = 4 * 864e5;     // a match more than 4 days from its round's middle was rearranged
const CALLED_OFF = new Set(["PST", "CANC", "ABD", "AWD", "WO"]);
const roundName = (r) => r.replace(/^Regular Season - /, "Round ").replace(/^League Stage - /, "League phase ");
// A competition's rounds in date order: [{ key, label, matches, first, last }]. Group stages
// (cup rounds named after the group) go by week instead, one "Group stage" entry per week.
function matchRounds(lid) {
  const cache = state.roundsCache ||= new Map();
  if (cache.has(lid)) return cache.get(lid);
  const byKey = new Map();
  for (const m of matchesTab()) {
    if (m.league !== lid) continue;
    let key = m.round || "", label = roundName(key);
    if (!key || /^Group /.test(key)) {
      const d = new Date(m.kickoff);
      d.setDate(d.getDate() - ((d.getDay() + 6) % 7));        // that week's Monday
      key = `w:${localDateStr(d)}`;
      label = "Group stage";
    }
    if (!byKey.has(key)) byKey.set(key, { key, label, matches: [] });
    byKey.get(key).matches.push(m);
  }
  const rounds = [...byKey.values()];
  for (const r of rounds) {
    r.matches.sort((a, b) => a.kickoff.localeCompare(b.kickoff));
    const times = r.matches.map((m) => Date.parse(m.kickoff));
    const mid = times[Math.floor(times.length / 2)];
    r.mid = mid;
    const own = times.filter((t) => Math.abs(t - mid) <= ROUND_WINDOW);    // its scheduled dates
    r.first = Math.min(...own);
    r.last = Math.max(...own);
    // still to come: a match in its own window that hasn't been played (or called off)
    r.pending = r.matches.some((m) => !FINISHED.has(m.status) && !CALLED_OFF.has(m.status)
      && Math.abs(Date.parse(m.kickoff) - mid) <= ROUND_WINDOW);
  }
  rounds.sort((a, b) => a.mid - b.mid);
  cache.set(lid, rounds);
  return rounds;
}
// The round on now or next up: the first with matches still to play, else the last
function nextRound(lid) {
  const rounds = matchRounds(lid);
  return (rounds.find((r) => r.pending) || rounds[rounds.length - 1])?.key ?? null;
}
function roundDates(r) {
  const a = fmtShortDate(new Date(r.first).toISOString()), b = fmtShortDate(new Date(r.last).toISOString());
  return a === b ? a : `${a} – ${b}`;
}
function setRound(key) {
  const lid = matchSingleLeague();
  const r = matchRounds(lid).find((x) => x.key === key);
  if (!r) return;
  state.round = key;
  state.date = localDateStr(new Date(r.first));     // the day shown if you leave rounds
  renderMatches();
}
function stepRound(delta) {
  const rounds = matchRounds(matchSingleLeague());
  const i = rounds.findIndex((r) => r.key === state.round);
  const r = rounds[Math.min(rounds.length - 1, Math.max(0, i + delta))];
  if (r) setRound(r.key);
}

// Squad lines on match cards: both clubs' files load when the card comes into view
const squadObserver = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) {        // (watches the card: the line is hidden until filled)
    squadObserver.unobserve(e.target);
    const line = e.target.querySelector(".squad-line");
    if (line) fillSquadLine(line);
  }
}, { rootMargin: "200px" }) : null;
async function fillSquadLine(el) {
  const m = state.data.matches.find((x) => x.id === Number(el.dataset.fixture));
  if (!m) return;
  await loadPlayers();
  if (!state.players) return;
  state.injuries ||= await getJsonOrNull("data/injuries.json");
  const [h, a] = await Promise.all([loadClub(m.home), loadClub(m.away)]);
  const sh = h && squadStrength(m.home, h, m), sa = a && squadStrength(m.away, a, m);
  if (!sh || !sa) return;
  const badge = (icon, value, label, cls = "") => `<span class="squad-badge${cls ? ` ${cls}` : ""}" title="${label}: ${Math.round(value)}"><span class="ico">${icon}</span>${Math.round(value)}</span>`;
  const trend = (value, normal) => normal == null ? "" : Math.round(value) > Math.round(normal) ? "good" : Math.round(value) < Math.round(normal) ? "bad" : "same";
  // worked out here from the club files' expected minutes, so labelled as not being model inputs
  const est = " (estimated on this page from expected minutes; not a model input)";
  const nameHtml = (s) => badge("🛡️", s.defence, `Defence${est}`) + badge("⚔️", s.attack, `Attack${est}`);
  const overallHtml = (s, normal) => badge("⚽", s.strength, `Overall squad rating${est}${normal == null ? "" : `; recent starting XIs ${Math.round(normal)}`}`, trend(s.strength, normal));
  const card = el.closest(".match-card");
  card.querySelector('[data-squad-team="home"]').innerHTML = nameHtml(sh);
  card.querySelector('[data-squad-team="away"]').innerHTML = nameHtml(sa);
  card.querySelector('[data-squad-overall="home"]').innerHTML = overallHtml(sh, m.home_recent_xi);
  card.querySelector('[data-squad-overall="away"]').innerHTML = overallHtml(sa, m.away_recent_xi);
}
function observeSquadLines() {
  document.querySelectorAll("#matches-list .squad-line[hidden]:not([data-watched])").forEach((el) => {
    el.dataset.watched = "1";
    squadObserver ? squadObserver.observe(el.closest(".match-card")) : fillSquadLine(el);
  });
}
new MutationObserver(observeSquadLines).observe($("#matches-list"), { childList: true, subtree: true });
function renderMatches(menu = true) {
  state.drawn.add("matches");
  const container = $("#matches-list");
  $("#date-input").value = state.date;
  if (menu) renderMatchFilters();
  // One competition: the round bar (‹ round › Next) and that round's matches by day
  const lid = matchSingleLeague();
  const rounds = lid != null ? matchRounds(lid) : [];
  const byRound = rounds.length > 0;
  $("#date-input").hidden = byRound;
  $("#round-select").hidden = !byRound;
  $("#date-today").textContent = byRound ? "Next" : "Today";
  $("#date-today").title = byRound ? "The round on now or next up" : "";
  $("#date-prev").setAttribute("aria-label", byRound ? "Previous round" : "Previous day");
  $("#date-next").setAttribute("aria-label", byRound ? "Next round" : "Next day");
  if (byRound) {
    if (!rounds.some((r) => r.key === state.round)) state.round = nextRound(lid);
    const i = rounds.findIndex((r) => r.key === state.round);
    $("#round-select").innerHTML = rounds.map((r) =>
      `<option value="${escapeHtml(r.key)}"${r.key === state.round ? " selected" : ""}>${escapeHtml(r.label)} · ${escapeHtml(roundDates(r))}</option>`).join("");
    $("#date-prev").disabled = i <= 0;
    $("#date-next").disabled = i >= rounds.length - 1;
    const days = new Map();
    for (const m of rounds[i].matches) {
      const d = localDateStr(new Date(m.kickoff));
      if (!days.has(d)) days.set(d, []);
      days.get(d).push(m);
    }
    container.innerHTML = [...days.entries()].map(([d, list]) => {
      const key = `d:${d}`, collapsed = state.collapsed.has(key);
      return `
      <div class="comp-group${collapsed ? " collapsed" : ""}" data-comp="${key}">
        <div class="comp-group-header" role="button" tabindex="0" aria-expanded="${!collapsed}">
          <span class="comp-group-caret" aria-hidden="true">${collapsed ? "&#9656;" : "&#9662;"}</span>
          <span class="comp-group-name">${escapeHtml(fmtDay(parseDateInput(d)))}</span>
          <span class="comp-group-count">${list.length}</span>
        </div>
        <div class="card-list">${list.map(matchCard).join("")}</div>
      </div>`;
    }).join("");
    return;
  }
  $("#date-prev").disabled = $("#date-next").disabled = false;
  const ids = matchLeagueIds();
  const day = state.date;
  const shown = matchesTab()
    .filter((m) => !ids || ids.includes(m.league))
    .filter((m) => localDateStr(new Date(m.kickoff)) === day);

  if (!shown.length) {
    const upcoming = matchesTab()
      .filter((m) => (!ids || ids.includes(m.league)) && localDateStr(new Date(m.kickoff)) > day)[0];
    container.innerHTML = `<div class="empty-state">No matches on ${escapeHtml(fmtDay(parseDateInput(day)))}.${upcoming
      ? `<br><br><button type="button" class="filter-chip" data-goto="${localDateStr(new Date(upcoming.kickoff))}">Next: ${escapeHtml(fmtDay(upcoming.kickoff))}</button>` : ""}</div>`;
    return;
  }

  const groups = new Map();
  shown.forEach((m) => { if (!groups.has(m.league)) groups.set(m.league, []); groups.get(m.league).push(m); });
  const orderOf = (id) => { const i = GROUP_ORDER.indexOf(id); return i === -1 ? 999 : i; };
  const ordered = [...groups.keys()].sort((a, b) => orderOf(a) - orderOf(b) || compLabel(a).localeCompare(compLabel(b)));

  container.innerHTML = ordered.map((id) => {
    const list = groups.get(id);
    const collapsed = state.collapsed.has(id);
    return `
      <div class="comp-group${collapsed ? " collapsed" : ""}" data-comp="${id}">
        <div class="comp-group-header" role="button" tabindex="0" aria-expanded="${!collapsed}">
          <span class="comp-group-caret" aria-hidden="true">${collapsed ? "&#9656;" : "&#9662;"}</span>
          <span class="comp-group-name">${escapeHtml(compLabel(id))}</span>
          <span class="comp-group-count">${list.length}</span>
        </div>
        <div class="card-list">${list.map(matchCard).join("")}</div>
      </div>`;
  }).join("");
}

function stepDate(delta) {
  const d = parseDateInput(state.date);
  d.setDate(d.getDate() + delta);
  state.date = localDateStr(d);
  renderMatches();
}

// ------------------------------------------------------------------ rankings table
// a value's place among every ranked club on that measure (Current Strength = current, Baseline
// Strength = lt), as the
// badge colours: top 5% green, top 20% amber, top half orange, the rest red
const sortedBy = {};
function clubTier(key, v) {
  const s = sortedBy[key] ||= state.rankings.map((x) => x[key]).sort((a, b) => b - a);
  let lo = 0, hi = s.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (s[m] > v) lo = m + 1; else hi = m; }
  const share = (lo + 1) / s.length;
  return share <= 0.05 ? 4 : share <= 0.2 ? 3 : share <= 0.5 ? 2 : 1;
}
// the Baseline column's heading, shortened on phones where the full word doesn't fit
const BASELINE_TH = `<span class="th-full">Baseline</span><span class="th-short">Base</span>`;
const formChip = (v) => `<span class="rel-chip rel-${clubTier("current", v)}">${Math.round(v)}</span>`;
const eloChip = (v) => `<span class="rel-chip rel-${clubTier("lt", v)}">${Math.round(v)}</span>`;
function relTier(r) { return r >= 90 ? 4 : r >= 70 ? 3 : r >= 40 ? 2 : 1; }
function formHtml(f) {
  if (f == null) return "";
  const v = Math.round(f);
  return v > 0 ? `<span class="form-up">+${v}</span>` : v < 0 ? `<span class="form-down">${v}</span>` : "0";
}

const POS_LABEL = { G: "GK", D: "DEF", M: "MID", F: "FWD" };
const rankTier = (r) => r >= 80 ? 4 : r >= 60 ? 3 : r >= 35 ? 2 : 1;
function rankChipSmall(r) {
  if (r == null) return "–";
  return `<span class="rel-chip rel-${rankTier(r)}">${Math.round(r)}</span>`;
}

const TOP_ROWS = 10;
// Show the first TOP_ROWS rows; the rest scroll inside the box
// capped=false (a single league) shows every row
// Long lists (All, search): the box fills the rest of the screen - at least TOP_ROWS rows -
// and scrolls inside. A single league shows every row.
function fitTopRows(wrap, capped = true) {
  const box = wrap.querySelector(".table-scroll");
  if (!box) return;
  const rows = box.querySelectorAll("tbody tr");
  if (!capped || rows.length <= TOP_ROWS) { box.style.maxHeight = "none"; return; }
  let minH = box.querySelector("thead").offsetHeight;
  for (let i = 0; i < TOP_ROWS; i++) minH += rows[i].offsetHeight;
  const room = window.innerHeight - box.getBoundingClientRect().top - 12;
  box.style.maxHeight = `${Math.max(minH + 2, room)}px`;
}
window.addEventListener("resize", () => {
  if (!state.rankings || state.tab !== "table") return;
  fitTopRows($("#table-wrap"), tableFilterIsWide() || !!state.tableSearch.trim());
  fitYearsBox($("#table-wrap"));
});
// Players with the years open: the box widens to the right, as far as the window allows (16px
// short of its edge), to fit the extra columns, and the search box above widens with it; their
// left edges and the page don't move
function fitYearsBox(wrap) {
  const box = wrap.querySelector(".table-scroll"), search = $("#table-search");
  search.style.width = "";
  if (!box) return;
  box.style.width = "";
  const table = box.querySelector("table.players.years");
  if (!table) return;
  const room = document.documentElement.clientWidth - box.getBoundingClientRect().left - 16;
  const need = table.scrollWidth + box.offsetWidth - box.clientWidth;   // plus its borders
  if (need > box.offsetWidth) box.style.width = search.style.width = `${Math.max(box.offsetWidth, Math.min(need, room))}px`;
  // #, Player, Pos and Age stay put when it scrolls sideways: each column's left edge, for the CSS
  // (summed widths: a sticky cell's offsetLeft moves as it sticks)
  let left = 0;
  [...table.tHead.rows[0].cells].slice(0, 4).forEach((c, i) => {
    table.style.setProperty(`--fz${i + 1}`, `${left}px`);
    left += c.getBoundingClientRect().width;
  });
}

function loadPlayerSeasons() {
  if (state.playerSeasons || state.playerSeasonsLoading) return;
  state.playerSeasonsLoading = getJson("data/player_seasons.json").then((d) => { state.playerSeasons = d; }).catch(() => {});
}
// Club and player files carry their own rows of the season detail (positions). One exported
// before they did has none, so the whole file is loaded for it as before
function seasonsFor(...files) {
  if (!files.some((f) => f && !f.positions)) return null;
  loadPlayerSeasons();
  return state.playerSeasonsLoading;
}
// Hover text for a season cell: his age that season (his age now for the current season, one
// less for each season before), then per club "Team – club rank" and
// "minutes – match rating – goals G, assists A"
function playerCellTip(pid, key) {
  const detail = state.playerSeasons;
  if (!detail) return "Loading…";
  const pl = (state.playersById ||= new Map(state.players.list.map((x) => [String(x.id), x]))).get(pid);
  const seasons = state.players.seasons || [];
  const ageLine = pl?.age != null ? `Age ${pl.age - (seasons[0] - Number(key))}
` : "";
  const spells = detail.players?.[pid]?.[key];
  const i = seasons.indexOf(Number(key));
  if (pl?.estimated?.includes(i)) {
    const club = spells?.[0] ? `${detail.teams?.[spells[0][0]] || teamName(spells[0][0])} – ${spells[0][2] ?? "–"}\n` : "";
    return ageLine + club + "Not in a covered league this season\nEstimated from his other seasons and age";
  }
  if (!spells?.length) return ageLine + "No minutes";
  const club = (id) => detail.teams?.[id] || teamName(id);
  return ageLine + spells.map(([team, mins, rank, rating, goals, assists]) =>
    `${club(team)} – ${rank == null ? "–" : rank}\n${mins.toLocaleString()} mins – ${rating == null ? "–" : rating.toFixed(2)} – ${goals ?? 0} G, ${assists ?? 0} A`)
    .join("\n\n");
}

function renderPlayers() {
  const wrap = $("#table-wrap");
  if (!state.players) { wrap.innerHTML = `<div class="empty-state">${state.players === undefined ? "Loading players…" : "No player ranks yet."}</div>`; if (loadFailed("players")) wrap.innerHTML = loadError("the players"); return; }
  const ids = tableLeagueIds();
  const q = state.tableSearch.trim().toLowerCase();
  const all = tableFilterIsWide();
  let rows = q ? state.players.list.filter((p) => playerSearchMatch(p, q))
               : state.clubs?.size ? state.players.list
               : isCupFilter(state.tableFilter) ? state.players.list.filter((p) => euroTeams(state.tableFilter)?.has(p.team))
               : ids === null ? state.players.list : state.players.list.filter((p) => ids.includes(p.league));
  if (!q && !state.clubs?.size) rows = rows.filter((p) => !isExcluded(p.league));
  rows = rows.filter(playerVisible);
  // Sort: a season rank ("s2026", the current season by default; highest first) or age
  // (youngest first); blanks last
  // Collapsed: Age and Ability only. Expanded (the Years button): past seasons before Ability and
  // the projected ones (his Ability moved along his position's age curve) after it
  const seasons = state.players.seasons || [];
  const future = state.players.futureSeasons || [];
  const open = state.playerYears;
  const shown = open ? seasons : seasons.slice(0, 1);
  const groups = selectedGroups();
  let key = state.playerSort === "pos" && !groups.length ? `s${seasons[0]}` : state.playerSort || (groups.length ? "pos" : `s${seasons[0]}`);
  if (!open && /^[sf]\d/.test(key) && key !== `s${seasons[0]}`) key = `s${seasons[0]}`;   // a hidden column
  if (groups.length && key === `s${seasons[0]}`) key = "pos";                                  // Ability is shown as "As ST"
  const val = (p) => key === "pos" ? posRank(p, groups) : key.startsWith("s") ? p.seasons?.[seasons.indexOf(Number(key.slice(1)))]
    : key.startsWith("f") ? p.future?.[future.indexOf(Number(key.slice(1)))]
    : key === "ga" ? (p.season ? p.season[2] + p.season[3] + p.season[2] / 1000 : null)   // goals break ties
    : key === "rating" ? p.season?.[1] : p[key];
  rows = key === "age"
    ? rows.slice().sort((a, b) => (a.age ?? 999) - (b.age ?? 999))
    : rows.slice().sort((a, b) => (val(b) ?? -1) - (val(a) ?? -1));
  const th = (k, label, tip, cls = "") =>
    `<th class="num sortable${key === k ? " active" : ""}${cls}" tabindex="0"${key === k ? ` aria-sort="${k === "age" ? "ascending" : "descending"}"` : ""} data-sort="${k}" data-tip="${escapeHtml(tip + " Click to sort.")}">${label}</th>`;
  const seasonName = (y) => `${y}/${String(y + 1).slice(2)}`;
  // With a position filter, "As ST" takes Ability's place (Ability is his rank in his own position)
  // the + / − (other seasons) sits in the Ability (or "As ST") heading, and the values centre under both
  const yearsBtn = future.length || seasons.length > 1 ? `<button type="button" class="years-btn" data-years aria-expanded="${open}" aria-label="${open ? "Hide" : "Show"} other seasons" title="${open ? "Hide" : "Show"} past and projected seasons">${open ? "−" : "+"}</button>` : "";
  const nowHead = (text) => `<span class="now-head">${text}${yearsBtn}</span>`;
  const posTh = groups.length ? th("pos", nowHead(groups.length === 1 ? `As ${groups[0]}` : "In pos"), `How good he is now as ${groups.map((g) => GROUP_SINGLE[g]).join(" / ")}: his recent stats scored as that position against its players, with up to 6 points off for a position he hasn't played much (none once it's 40% of his starts). Only positions he has started in get a number. With several positions picked, his best of them.`, " col-posrank") : "";
  if (!rows.length) { wrap.innerHTML = `<div class="empty-state">No players match these filters.</div>`; return; }
  playerPlaces();
  wrap.innerHTML = `
    <div class="table-scroll"><table class="leaderboard players${open ? " years" : ""}">
      <thead><tr>
        <th data-tip="Position in this list, in the current sort order.">#</th>
        <th data-tip="Player, with his club's badge (click it for the club's page) and his country's flag (click it for the national team).">Player</th>
        <th class="num" data-tip="Position: the role he has started in most over his last 20 appearances.">Pos</th>
        ${th("age", "Age", "Age today (sorts youngest first).", " col-age")}
        <th class="num col-wrank" data-tip="World rank: his place among every listed player by Ability, whatever this list is filtered or sorted by.">World</th>
        <th class="num col-lrank" data-tip="League rank: his place by Ability among the listed players in his club's league.">Lg</th>
        ${th("ga", "G/A", "Goals and assists this season, all his clubs (7G 4A), with his match rating under them where the Rtg column doesn't fit. Sorts by the two added together.", " col-ga")}
        ${th("rating", "Rtg", "Average match rating this season (API-Football's, weighted by minutes), all his clubs. Greyed when he's played under a third of his clubs' minutes since he joined (a squad player, or back from injury), so it rests on little.", " col-rtg")}
        ${shown.map((y, i) => [y, i]).reverse().map(([y, i]) => i === 0 && groups.length ? posTh : th(`s${y}`, i === 0 ? nowHead("Ability") : `${String(y).slice(2)}/${String(y + 1).slice(2)}`, `${i === 0 ? "Underlying Ability: the model's estimate of how good he is now (not his recent match ratings or this season's totals, which are on his page). " : ""}Rank for the ${seasonName(y)} season (the ${y} season in calendar-year leagues such as MLS and Norway${i === 0 ? "; so far" : ""}): his club's level that season, moved by how his stats compare with other players in his position (elite seasons earn extra, and positions are weighted). Squad players who play little are marked down. Every player follows the typical age curve for his position from a level of his own, and only moves off it as far as his minutes that season justify, so a thin season (an injury year, the start of a season) stays close to his curve. A season with no minutes in these leagues is estimated from his other seasons and his age, and shown outlined.`, ` col-season col-s${i}${i === 0 ? " col-now" : ""}`)).join("")}
        ${open ? future.map((y, j) => th(`f${y}`, `${String(y).slice(2)}/${String(y + 1).slice(2)}`, `Projected for ${seasonName(y)}: his Ability moved along the typical age curve for his position, from his age now to his age that season (young players rise, from 31 (33 for keepers) they decline, faster each year). A guide, not a forecast of his form.`, ` col-season col-future col-f${j}`)).join("") : ""}
      </tr></thead>
      <tbody>${rows.slice(0, FIRST_ROWS).map((p, i) => playerRow(p, i, shown, groups, open ? future : [])).join("")}</tbody>
    </table></div>`;
  fitTopRows(wrap, all || !!q);
  fitYearsBox(wrap);
  // The rest of the rows go in BATCH_ROWS at a time as the bottom of the list scrolls into view
  // (inside the box when it scrolls, else on the page), so thousands of rows are never built at
  // once; a newer render drops the old observer
  state.playerObserver?.disconnect();
  if (rows.length <= FIRST_ROWS) return;
  const box = wrap.querySelector(".table-scroll");
  const tbody = wrap.querySelector("tbody");
  const sentinel = document.createElement("div");
  box.appendChild(sentinel);
  let at = FIRST_ROWS;
  const observer = state.playerObserver = new IntersectionObserver((entries) => {
    if (!entries.some((e) => e.isIntersecting)) return;
    tbody.insertAdjacentHTML("beforeend", rows.slice(at, at + BATCH_ROWS).map((p, j) => playerRow(p, at + j, shown, groups, open ? future : [])).join(""));
    at += BATCH_ROWS;
    if (at >= rows.length) { observer.disconnect(); sentinel.remove(); }
    else { observer.unobserve(sentinel); observer.observe(sentinel); }   // re-check: still in view -> load again
  }, { root: getComputedStyle(box).maxHeight === "none" ? null : box, rootMargin: "0px 0px 600px 0px" });
  observer.observe(sentinel);
}

const FIRST_ROWS = 100, BATCH_ROWS = 100;
function playerRow(p, i, seasons, groups = selectedGroups(), future = []) {
  const place = state.playerPlaces?.get(p.id);
  const thin = p.season?.[4] && p.season[0] < p.season[4] / 3;     // under a third of his clubs' minutes
  return `
        <tr${p.team ? ` data-team="${p.team}"` : ""} data-player="${p.id}">
          <td>${i + 1}</td>
          <td><div class="pl-cell">${p.team ? `<a class="pl-badge-link" href="${clubHref(p.team)}" title="${escapeHtml(teamName(p.team))}" aria-label="${escapeHtml(teamName(p.team))}">${clubCrest(p.team, "club-logo pl-badge")}</a>` : `<span class="club-logo pl-badge" title="Club not known"></span>`}${personChip(p.name)}
            <div class="pl-text"><div class="pl-name"><a class="player-link" href="#/player/${p.id}" title="${escapeHtml(p.name)}"><span class="pn-full">${escapeHtml(p.name)}</span><span class="pn-short">${escapeHtml(shortName(p.name))}</span></a>${playerFlag(p.nationality)}</div>
              <div class="pl-club">${p.team ? escapeHtml(teamName(p.team)) : "Club not known"}${p.league != null && leagueShort(p.league) ? ` · ${escapeHtml(leagueShort(p.league))}` : ""}</div></div></div></td>
          <td class="num">${POS_LABEL[p.position] || escapeHtml(p.position || "")}</td>
          <td class="num col-age">${p.age ?? `<span class="dim">–</span>`}</td>
          <td class="num col-wrank">${place?.world.toLocaleString() ?? `<span class="dim">–</span>`}</td>
          <td class="num col-lrank"${place?.lg ? ` title="${ordinal(place.lg)} of ${place.lgOf} in the ${escapeHtml(leagueShort(p.league))}"` : ""}>${place?.lg ?? `<span class="dim">–</span>`}</td>
          <td class="num col-ga">${p.season ? `${p.season[2]}G ${p.season[3]}A` : `<span class="dim">–</span>`}${p.season?.[1] != null ? `<span class="ga-rtg${thin ? " thin" : ""}">${p.season[1].toFixed(2)}</span>` : ""}</td>
          <td class="num col-rtg${thin ? " thin" : ""}">${p.season?.[1] != null ? p.season[1].toFixed(2) : `<span class="dim">–</span>`}</td>
          ${seasons.map((y, k) => [y, k]).reverse().map(([y, k]) => k === 0 && groups.length ? `<td class="num col-posrank">${posRank(p, groups) == null ? `<span class="dim">–</span>` : rankChipSmall(posRank(p, groups))}</td>` : `<td class="num col-season col-s${k}${k === 0 ? " col-now" : ""} tip-cell" data-key="${y}">${p.seasons?.[k] == null ? `<span class="dim">–</span>` : p.estimated?.includes(k) ? `<span class="est">${rankChipSmall(p.seasons[k])}</span>` : rankChipSmall(p.seasons[k])}</td>`).join("")}
          ${future.map((y, j) => `<td class="num col-season col-future col-f${j}">${p.future?.[j] == null ? `<span class="dim">–</span>` : rankChipSmall(p.future[j])}</td>`).join("")}
        </tr>`;
}

// Club search: every word has to start a word of the club's name, its league or that league's
// country, ignoring accents and punctuation ("england league one", "man city", "munchen").
// Short forms count too: nicknames and abbreviations below, the initials of longer names
// ("psg", "qpr"), the site's league labels ("prem", "l1") and flag codes ("ned", "us").
// Clubs outside this season's leagues only match by name.
const foldText = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const CLUB_ALIASES = {
  "Arsenal": "gunners afc", "Aston Villa": "villa avfc", "Bournemouth": "cherries afcb", "Brentford": "bees",
  "Brighton": "seagulls bhafc brighton and hove albion", "Chelsea": "cfc blues", "Crystal Palace": "palace cpfc eagles",
  "Everton": "efc toffees", "Fulham": "cottagers ffc", "Ipswich": "tractor boys itfc", "Leeds": "lufc leeds united",
  "Leicester": "foxes lcfc", "Liverpool": "lfc reds", "Manchester City": "man city mcfc citizens",
  "Manchester United": "man utd man united mufc red devils", "Newcastle": "toon nufc magpies newcastle united",
  "Nottingham Forest": "forest nffc", "Southampton": "saints", "Sunderland": "safc black cats",
  "Tottenham": "spurs thfc tottenham hotspur", "West Ham": "hammers whufc irons west ham united",
  "Wolves": "wolverhampton wanderers wwfc", "Burnley": "clarets", "Coventry": "sky blues ccfc", "Hull City": "tigers",
  "Middlesbrough": "boro", "Sheffield Utd": "blades sheffield united sufc", "Sheffield Wednesday": "owls swfc",
  "West Brom": "wba baggies albion west bromwich", "QPR": "queens park rangers", "Birmingham": "blues bcfc",
  "Norwich": "canaries ncfc", "Stoke City": "potters", "Derby": "rams", "Millwall": "lions", "Preston": "pne",
  "Swansea": "swans jacks", "Cardiff": "bluebirds", "Portsmouth": "pompey", "Blackburn": "rovers",
  "Charlton": "addicks", "Watford": "hornets", "Bristol City": "robins", "Plymouth": "argyle", "Huddersfield": "terriers",
  "Barcelona": "barca fcb", "Real Madrid": "rmcf los blancos", "Atletico Madrid": "atleti atm", "Athletic Club": "bilbao",
  "Real Sociedad": "la real", "Real Betis": "betis", "Bayern München": "bayern munich fcb", "Borussia Dortmund": "bvb",
  "Borussia Mönchengladbach": "gladbach bmg", "Bayer Leverkusen": "b04", "RB Leipzig": "rbl", "Eintracht Frankfurt": "sge",
  "VfB Stuttgart": "vfb", "Inter": "internazionale inter milan", "AC Milan": "milan acm rossoneri", "Juventus": "juve",
  "AS Roma": "roma", "Paris Saint Germain": "psg paris sg", "Marseille": "om olympique de marseille",
  "Lyon": "ol olympique lyonnais", "Sporting CP": "sporting lisbon scp", "Benfica": "slb", "FC Porto": "porto",
  "PSV Eindhoven": "psv", "Club Brugge KV": "club bruges", "Union St. Gilloise": "usg union saint gilloise",
  "Galatasaray": "gala cimbom", "Fenerbahçe": "fener", "Beşiktaş": "besiktas bjk", "Olympiakos Piraeus": "olympiacos",
};
const LEAGUE_ALIASES = {
  39: "epl pl prem", 40: "champ efl", 41: "l1 league 1 efl", 42: "l2 league 2 efl", 43: "nl non league",
  50: "nln non league", 51: "nls non league", 140: "laliga liga", 141: "segunda liga 2", 135: "serie a", 136: "serie b",
  78: "buli bl", 79: "2 bundesliga zweite", 61: "l1 ligue 1", 62: "l2 ligue 2", 94: "liga portugal", 179: "spfl prem",
  144: "jpl belgian pro league", 203: "super lig", 253: "mls", 71: "brasileirao", 262: "liga mx",
};
const COUNTRY_ALIASES = {
  "England": "uk gb eng", "Scotland": "uk gb sco", "USA": "us united states america", "Netherlands": "holland ned dutch",
  "Czech-Republic": "czechia cze", "Turkey": "turkiye tur", "Spain": "esp", "Germany": "ger deu", "Switzerland": "sui",
  "Croatia": "cro", "Denmark": "den", "Portugal": "por", "Greece": "gre", "Saudi-Arabia": "ksa", "Bosnia": "bih herzegovina",
};
const initials = (words) => words.length >= 2 ? words.map((w) => w[0]).join("") : "";
const foldedAliases = new Map(Object.entries(CLUB_ALIASES).map(([n, a]) => [foldText(n), a]));
const searchIndex = new Map();
function clubSearchText(r) {
  let text = searchIndex.get(r.team);
  if (text != null) return text;
  const name = foldText(teamName(r.team));
  const parts = [name, initials(name.split(" ")), foldedAliases.get(name) || ""];
  if (/\bunited\b/.test(name)) parts.push("utd");
  if (/\butd\b/.test(name)) parts.push("united");
  const c = r.in_league ? state.data.competitions[r.league] : null;
  if (c) {
    const league = foldText(c.name), country = countryDisplay(c.country);
    const label = [...PRIMARY_COMPS, ...TABLE_COMPS].find((x) => x.id === String(r.league))?.label;
    parts.push(league, initials(league.split(" ")), foldText(SHORT_NAMES[r.league]), foldText(label),
      LEAGUE_ALIASES[r.league] || "", foldText(country), COUNTRY_ALIASES[c.country] || "",
      (FLAG_CODES[country] || "").replace("gb-", ""));
  }
  text = " " + parts.filter(Boolean).join(" ") + " ";
  searchIndex.set(r.team, text);
  return text;
}
// Players search: his name as typed ("yamal"), or every word starting a word of his name or of
// his club's search text, so club short forms work too ("man city", "haaland city", "spurs")
let rankingByTeam = null;
function playerSearchMatch(p, q) {
  if (p.name.toLowerCase().includes(q)) return true;
  const words = foldText(q).split(" ").filter(Boolean);
  if (!words.length) return false;
  rankingByTeam ??= new Map(state.rankings.map((r) => [r.team, r]));
  const r = p.team ? rankingByTeam.get(p.team) : null;
  const text = ` ${foldText(p.name)} ${r ? clubSearchText(r) : ` ${foldText(teamName(p.team))} `}`;
  return words.every((w) => text.includes(" " + w));
}
function clubSearchRows(q) {
  const words = foldText(q).split(" ").filter(Boolean);
  return state.rankings.filter((r) => {
    const text = clubSearchText(r);
    return words.every((w) => text.includes(" " + w));
  });
}

// ---- World and league places, worked out once. Clubs: by Baseline Strength among every ranked
// club (as on the club page), and among the clubs playing in the same league this season.
// Players: by Ability (this season's rank) among every listed player, and within his league.
// A tie shares the higher place.
function placeIn(sorted, v) {        // sorted highest first
  let lo = 0, hi = sorted.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] > v) lo = m + 1; else hi = m; }
  return lo + 1;
}
function sortedGroups(items, value, group) {
  const all = [], by = new Map();
  for (const x of items) {
    const v = value(x);
    if (v == null) continue;
    all.push(v);
    const g = group(x);
    if (g != null) (by.get(g) || by.set(g, []).get(g)).push(v);
  }
  const desc = (a, b) => b - a;
  all.sort(desc);
  for (const l of by.values()) l.sort(desc);
  return { all, by };
}
function clubPlaces() {
  if (!state.clubPlaces) {
    const { all, by } = sortedGroups(state.rankings, (r) => r.lt, (r) => r.in_league ? r.league : null);
    state.clubPlaces = new Map(state.rankings.map((r) => {
      const lg = r.in_league ? by.get(r.league) : null;
      return [r.team, { world: placeIn(all, r.lt), dom: lg ? placeIn(lg, r.lt) : null, domOf: lg?.length ?? null }];
    }));
  }
  return state.clubPlaces;
}
const clubWorld = (team) => team == null ? null : clubPlaces().get(team)?.world ?? null;
const abilityOf = (p) => p.seasons?.[0] ?? null;
function playerPlaces() {
  if (!state.playerPlaces) {
    const list = state.players.list;
    const { all, by } = sortedGroups(list, abilityOf, (p) => p.league);
    state.playerPlaces = new Map(list.filter((p) => abilityOf(p) != null).map((p) => [p.id, {
      world: placeIn(all, abilityOf(p)), lg: p.league != null ? placeIn(by.get(p.league), abilityOf(p)) : null,
      lgOf: p.league != null ? by.get(p.league).length : null }]));
  }
  return state.playerPlaces;
}
const leagueShort = (lid) => SHORT_NAMES[lid] || state.data.competitions[lid]?.name || "";

// ---- Range filters on Players: each [min, max], null = open. They combine with the competition
// menu, Exclude, search and the age, position, club and nationality filters
const RANGES = {
  ab: { view: "players", label: "Ability", tip: "Underlying Ability, 0-100: the model's estimate of his level now" },
  crank: { view: "players", label: "Club world rank", tip: "His club's place among every ranked club by Baseline Strength (1 = strongest). Players without a ranked club drop out while this is set" },
  mins: { view: "players", label: "Minutes", tip: "Minutes over his last 20 appearances, the evidence behind his Ability" },
};
// Each range is a two-handled slider, like Age, over a list of stops: every whole Ability from the
// lowest to the highest, minutes a match (90) at a time, and club ranks finer at the top (1, 5, 10,
// 20 ...) so the top 50 can be picked out of thousands. A handle at either end leaves that end open
function rangeStops(k) {
  const cache = state.rangeStopsCache ||= {};
  if (cache[k]) return cache[k];
  let stops;
  if (k === "ab") {
    const v = state.players.list.map(abilityOf).filter((x) => x != null).map(Math.round);
    const lo = Math.min(...v), hi = Math.max(...v);
    stops = Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);
  } else if (k === "mins") {
    const hi = Math.ceil(Math.max(...state.players.list.map((p) => p.minutes || 0)) / 90) * 90;
    stops = Array.from({ length: hi / 90 + 1 }, (_, i) => i * 90);
  } else {
    const n = clubPlaces().size;
    stops = [...[1, 5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 400, 500, 750].filter((x) => x < n),
      ...Array.from({ length: Math.max(0, Math.ceil(n / 500) - 1) }, (_, i) => (i + 2) * 500).filter((x) => x < n), n];
  }
  return (cache[k] = stops);
}
// a handle's stop for a range end (one from a link needn't be on a stop: the nearest stop inside it)
function stopIndex(stops, v, end) {
  const n = stops.length - 1;
  if (v == null) return end ? n : 0;
  const i = end ? stops.findLastIndex((s) => s <= v) : stops.findIndex((s) => s >= v);
  return i < 0 ? (end ? 0 : n) : i;
}
const rangeOf = (k) => state.ranges[k] || [null, null];
function inRange(k, v) {
  const [lo, hi] = rangeOf(k);
  if (lo == null && hi == null) return true;
  return v != null && (lo == null || v >= lo) && (hi == null || v <= hi);
}
const rangeKeys = (view = state.tableView) => Object.keys(RANGES).filter((k) => RANGES[k].view === view);
const rangesOn = (view = state.tableView) => rangeKeys(view).filter((k) => rangeOf(k).some((v) => v != null)).length;
const playerInRanges = (p) => inRange("ab", abilityOf(p) == null ? null : Math.round(abilityOf(p)))   // as shown
  && inRange("crank", clubWorld(p.team)) && inRange("mins", p.minutes);
function renderRangeFilter() {
  const box = $("#range-filter");
  box.hidden = !state.rankings || (state.tableView === "players" && !state.players) || !rangeKeys().length;
  if (box.hidden) return;
  const slider = (k, end, max, label) => `<input type="range" min="0" max="${max}" step="1" data-rng="${k}" data-end="${end}" aria-label="${escapeHtml(label)}">`;
  box.innerHTML = `<div class="pos-head"><span>Ranges</span>
      <button type="button" class="pos-clear" data-range-clear${rangesOn() ? "" : " hidden"}>Clear</button></div>
    ${rangeKeys().map((k) => {
      const d = RANGES[k], n = rangeStops(k).length - 1;
      return `<div class="rng-row" data-rng-row="${k}" title="${escapeHtml(d.tip)}">
        <div class="age-head"><span>${d.label}</span><span class="rng-val"></span></div>
        <div class="age-slider"><div class="age-track"><div class="age-fill"></div></div>
          ${slider(k, 0, n, `${d.label}: from`)}${slider(k, 1, n, `${d.label}: to`)}</div></div>`;
    }).join("")}`;
  rangeKeys().forEach(drawRangeSlider);
}
// handles, fill and label for one range, from state.ranges
function drawRangeSlider(k) {
  const row = $(`#range-filter [data-rng-row="${k}"]`);
  if (!row) return;
  const stops = rangeStops(k), [lo, hi] = rangeOf(k), n = stops.length - 1;
  const a = stopIndex(stops, lo, 0), b = stopIndex(stops, hi, 1);
  row.querySelector('[data-end="0"]').value = a;
  row.querySelector('[data-end="1"]').value = b;
  const fill = row.querySelector(".age-fill");
  fill.style.left = `${(a / (n || 1)) * 100}%`;
  fill.style.right = `${100 - (b / (n || 1)) * 100}%`;
  const fmt = (v) => v.toLocaleString();
  row.querySelector(".rng-val").textContent = a === 0 && b === n ? "All"
    : a === 0 ? (k === "crank" ? `Top ${fmt(stops[b])}` : `Up to ${fmt(stops[b])}`)
    : b === n ? `${fmt(stops[a])}${k === "crank" ? " down" : "+"}` : `${fmt(stops[a])}–${fmt(stops[b])}`;
}
// Dragging: the handle and label move straight away, the table redraws at most once a frame and
// the menu's counts on release (as Age)
function onRangeInput(e, done) {
  const el = e.target.closest("[data-rng]");
  if (!el) return;
  const k = el.dataset.rng, stops = rangeStops(k), n = stops.length - 1, row = el.closest("[data-rng-row]");
  let a = Number(row.querySelector('[data-end="0"]').value), b = Number(row.querySelector('[data-end="1"]').value);
  if (a > b) { if (el.dataset.end === "0") a = b; else b = a; }       // handles can't cross
  state.ranges[k] = [a === 0 ? null : stops[a], b === n ? null : stops[b]];
  drawRangeSlider(k);
  $("#range-filter [data-range-clear]").hidden = !rangesOn();
  if (!state.rangeFrame)
    state.rangeFrame = requestAnimationFrame(() => { state.rangeFrame = 0; renderTable(); });
  if (done) renderTableFilters();
}
$("#range-filter").addEventListener("input", (e) => onRangeInput(e, false));
$("#range-filter").addEventListener("change", (e) => onRangeInput(e, true));
$("#range-filter").addEventListener("click", (e) => {
  if (!e.target.closest("[data-range-clear]")) return;
  for (const k of rangeKeys()) state.ranges[k] = [null, null];
  renderRangeFilter();
  renderTable();
  renderTableFilters();
});

// ---- Shareable Rankings: #/clubs?… and #/players?… carry the competition, search, sort and
// every filter, so a view can be bookmarked or sent. Rewritten in place as filters change (no
// history entry for each click) and read back by route() when the page opens on one.
const CLUB_SORTS = new Set(["lt", "trend", "current", "form"]), CLUB_SORT_DEFAULT = "current";
const rangeText = ([lo, hi]) => lo == null && hi == null ? null : `${lo ?? ""}-${hi ?? ""}`;
function tableHash() {
  const p = new URLSearchParams(), players = state.tableView === "players";
  if (state.tableFilter !== "all") p.set("c", state.tableFilter);
  if (state.tableSearch.trim()) p.set("q", state.tableSearch.trim());
  if (state.excluded.size) p.set("ex", [...state.excluded].join("|"));
  if (players ? state.playerSort : state.tableSort !== CLUB_SORT_DEFAULT) p.set("sort", players ? state.playerSort : state.tableSort);
  for (const k of rangeKeys()) { const t = rangeText(rangeOf(k)); if (t) p.set(k, t); }
  if (players) {
    const age = rangeText([state.ageMin, state.ageMax]);
    if (age) p.set("age", age);
    if (state.positions?.size) p.set("pos", [...state.positions].join(","));
    if (state.clubs?.size) p.set("club", [...state.clubs].join(","));
    if (state.nats?.size) p.set("nat", [...state.nats].join("|"));
  }
  const s = p.toString();
  return `#/${state.tableView}${s ? `?${s}` : ""}`;
}
function syncTableUrl() {
  if (state.tab !== "table" || !state.data) return;
  const h = tableHash();
  if (location.hash !== h) history.replaceState(null, "", h);
}
function openTableView(view, query) {
  const p = new URLSearchParams(query || "");
  const range = (k) => {
    const m = (p.get(k) || "").match(/^(\d*(?:\.\d+)?)-(\d*(?:\.\d+)?)$/);
    return m ? [m[1] === "" ? null : Number(m[1]), m[2] === "" ? null : Number(m[2])] : [null, null];
  };
  state.tableFilter = p.get("c") || "all";
  state.tableSearch = p.get("q") || "";
  state.excluded = new Set((p.get("ex") || "").split("|").filter(isExcludeKey));
  $("#table-search").value = state.tableSearch;
  const sort = p.get("sort");
  for (const k of rangeKeys(view)) state.ranges[k] = range(k);
  if (view === "players") {
    state.playerSort = sort && /^(age|pos|ga|rating|[sf]\d{4})$/.test(sort) ? sort : null;
    [state.ageMin, state.ageMax] = range("age");
    state.positions = new Set((p.get("pos") || "").split(",").filter((x) => PITCH_SPOTS.some(([s]) => s === x)));
    state.clubs = new Set((p.get("club") || "").split(",").map(Number).filter((n) => n > 0));
    state.nats = new Set((p.get("nat") || "").split("|").filter(Boolean));
  } else state.tableSort = CLUB_SORTS.has(sort) ? sort : CLUB_SORT_DEFAULT;
  state.drawn.add("table");          // setTableView draws it
  showTab("table");
  setTableView(view);
}

function renderTable() {
  state.drawn.add("table");
  syncTableUrl();
  if (state.tableView === "players") return renderPlayers();
  const wrap = $("#table-wrap");
  const ids = tableLeagueIds();
  const all = tableFilterIsWide();
  const q = state.tableSearch.trim().toLowerCase();
  const yearAgo = Date.now() - 365 * 864e5;
  // clubs playing in a tracked league this season (drops clubs relegated out of every tracked
  // league and cup-only sides)
  const active = state.rankings.filter((r) => r.in_league);
  let rows = ids === null ? active : active.filter((r) => ids.includes(r.league));
  if (isCupFilter(state.tableFilter)) {
    const teams = euroTeams(state.tableFilter);
    if (!teams) { loadEuroCups(); wrap.innerHTML = `<div class="empty-state">Loading the cups…</div>`; return; }
    rows = state.rankings.filter((r) => teams.has(r.team));
  }
  rows = rows.filter((r) => !isExcluded(r.league));
  if (q) rows = clubSearchRows(q);
  const places = clubPlaces();
  const key = state.tableSort;
  rows = rows.slice().sort((a, b) => (b[key] ?? -1e9) - (a[key] ?? -1e9));
  if (!rows.length) { wrap.innerHTML = `<div class="empty-state">No clubs ${state.excluded.size ? "match these filters" : "found"}.</div>`; return; }
  const th = (k, label, tip, cls = "") =>
    `<th class="num sortable${key === k ? " active" : ""}${cls}" tabindex="0"${key === k ? ` aria-sort="${k === "age" ? "ascending" : "descending"}"` : ""} data-sort="${k}" data-tip="${escapeHtml(tip + " Click to sort.")}">${label}</th>`;
  wrap.innerHTML = `
    <div class="table-scroll"><table class="leaderboard clubs">
      <thead><tr>
        <th data-tip="Position in this list, in the current sort order.">#</th>
        <th data-tip="Club badge. Click a club to open its page."><span class="th-club">Club</span></th>
        <th data-tip="Club name, with its country and league. Click a club to open its page.">Club</th>
        <th class="num" data-tip="World rank: place among every ranked club by Baseline Strength, whatever this list is filtered or sorted by.">World</th>
        <th class="num col-dom" data-tip="In league: place by Baseline Strength among the clubs in its league this season. TheCornerFC's ranking, not the league table (that's on the competition's page).">In lg</th>
        ${th("lt", BASELINE_TH, "Baseline Strength: the long-term Elo rating (LT ALGO), a smoothed rating weighted mostly to the average over the last 100 matches. Slow to move, and the better guide for matches months away.")}
        ${th("trend", "Gap", "Gap: Current Strength minus Baseline Strength. Green: rated above its long-term level; red: below it. A difference in level, not recent movement (see Last 6).", " col-gap")}
        ${th("current", "Current", "Current Strength: the Elo rating after the latest match. 100 points is worth a goal a game. It rises when a club does better than expected against that opponent, and falls when it does worse. Colour: green is the top 5% of all clubs, amber the top 20%, orange the top half, red the rest.")}
        ${th("form", "Last 6", "Recent movement: how much the club's Elo rating has changed over its last 6 matches.", " col-recent")}
      </tr></thead>
      <tbody>${rows.map((r, i) => `
        <tr data-team="${r.team}">
          <td>${i + 1}</td>
          <td>${clubCrest(r.team, "club-logo", `data-club="${r.team}" title="${escapeHtml(teamName(r.team))}"`)}</td>
          <td><div class="club-cell">${clubLink(r.team)}${q || all ? countryLeague(r.league) : ""}</div></td>
          <td class="num">${places.get(r.team)?.world.toLocaleString() ?? ""}</td>
          <td class="num col-dom" style="color:var(--text-muted)"${places.get(r.team)?.dom ? ` title="${ordinal(places.get(r.team).dom)} of ${places.get(r.team).domOf} in the ${escapeHtml(leagueShort(r.league))} by Baseline Strength"` : ""}>${places.get(r.team)?.dom ?? ""}</td>
          <td class="num">${eloChip(r.lt)}</td>
          <td class="num col-gap">${formHtml(r.trend)}</td>
          <td class="num">${formChip(r.current)}</td>
          <td class="num col-recent">${formHtml(r.form)}</td>
        </tr>`).join("")}
      </tbody>
    </table></div>
`;
  fitClubMeta(wrap);
  clubTableObserver.observe(wrap.querySelector(".table-scroll"));
  fitTopRows(wrap, all || !!q);
  fitYearsBox(wrap);
}

// ------------------------------------------------------------------ stats
const pct = (x, d = 1) => `${(100 * x).toFixed(d)}%`;
// ---- Position filter (Players view): a pitch of positions, attacking upwards
const PITCH_SPOTS = [       // [position, x %, y %]
  ["ST", 50, 12],
  ["LW", 18, 25], ["AM", 50, 27], ["RW", 82, 25],
  ["LM", 18, 41], ["CM", 50, 43], ["RM", 82, 41],
  ["LWB", 18, 57], ["DM", 50, 57], ["RWB", 82, 57],
  ["LB", 18, 72], ["CB", 50, 73], ["RB", 82, 72],
  ["GK", 50, 89],
];
const PITCH_LINES = `<svg viewBox="0 0 68 88" preserveAspectRatio="none" aria-hidden="true" fill="none"
    stroke="rgba(255,255,255,0.16)" stroke-width="0.6">
  <rect x="3" y="3" width="62" height="82" rx="1"/><line x1="3" y1="44" x2="65" y2="44"/>
  <circle cx="34" cy="44" r="7"/><rect x="17" y="3" width="34" height="12"/><rect x="26" y="3" width="16" height="5"/>
  <rect x="17" y="73" width="34" height="12"/><rect x="26" y="80" width="16" height="5"/></svg>`;
// A player shows under a position if it's his main one, or he started there for 25%+ of his
// starting minutes in the last 12 months (positions_12m)
const playsAt = (p) => new Set([p.position, ...(p.positions_12m || [])]);
// With the position filter on: the selected role groups, and a player's rank as the best of them
// (position_ranks: his stats scored as each position, less for one he hasn't played)
function selectedGroups() {
  return state.positions?.size ? [...new Set([...state.positions].map((r) => GROUP_OF[r]).filter(Boolean))] : [];
}
function posRank(p, groups) {     // null if he has never played any of them
  const v = groups.map((g) => p.position_ranks?.[g]).filter((x) => x != null);
  return v.length ? Math.max(...v) : null;
}
function playerVisible(p) {
  return inAgeRange(p) && (!state.positions?.size || [...playsAt(p)].some((r) => state.positions.has(r)))
    && (!state.clubs?.size || state.clubs.has(p.team))
    && (!state.nats?.size || state.nats.has(p.nationality)) && playerInRanges(p);
}
// ---- Club and nationality (Players view): pick one or more of each; they combine with the
// other filters, and a club pick shows that club's players whatever league is selected
// Built once: clubs {id, name (league added where two share a name), league}, clubs by league
// (in the league menu's order), and nationalities; each with a key for accent-free matching
const whoKey = (s) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
function whoOptions() {
  if (!state.whoCache && state.players) {
    const league = new Map(), names = new Map();
    for (const p of state.players.list) if (p.team && !league.has(p.team)) league.set(p.team, p.league);
    for (const t of league.keys()) {
      const n = teamName(t);
      names.set(n, (names.get(n) || 0) + 1);
    }
    const lgName = (lg) => SHORT_NAMES[lg] || state.data.competitions[lg]?.name || compLabel(lg);
    const clubs = [...league].map(([id, lg]) => {
      const n = teamName(id), name = names.get(n) > 1 ? `${n} (${lgName(lg)})` : n;
      return { id, name, league: lg, key: whoKey(name) };
    }).sort((a, b) => a.name.localeCompare(b.name));
    const order = tableCountries().flatMap((c) => c.leagues);
    const pos = (lg) => { const i = order.indexOf(Number(lg)); return i === -1 ? order.length : i; };
    const byLeague = new Map();
    for (const c of clubs) {
      if (!byLeague.has(c.league)) byLeague.set(c.league, []);
      byLeague.get(c.league).push(c);
    }
    const leagues = [...byLeague].map(([id, list]) => ({ id, name: lgName(id), clubs: list }))
      .sort((a, b) => pos(a.id) - pos(b.id) || a.name.localeCompare(b.name));
    const nats = [...new Set(state.players.list.map((p) => p.nationality).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b)).map((name) => ({ name, key: whoKey(name) }));
    state.whoCache = { clubs, byId: new Map(clubs.map((c) => [c.id, c])), leagues, nats };
  }
  return state.whoCache;
}
function renderWhoFilter() {
  const box = $("#who-filter");
  box.hidden = state.tableView !== "players" || !state.players;
  if (box.hidden) return;
  const { byId } = whoOptions();
  state.clubs ||= new Set();
  state.nats ||= new Set();
  $("#who-chips").innerHTML =
    [...state.clubs].map((t) => `<button type="button" class="who-chip" data-club="${t}" title="Remove">
       ${clubCrest(t, "club-logo")}${escapeHtml(byId.get(t)?.name || teamName(t))}<span class="x" aria-hidden="true">×</span></button>`).join("")
    + [...state.nats].map((n) => `<button type="button" class="who-chip" data-nat="${escapeHtml(n)}" title="Remove">
       ${flagImg(n) || `<span class="kind">Nat</span>`}${escapeHtml(n)}<span class="x" aria-hidden="true">×</span></button>`).join("");
  box.querySelector("[data-who-clear]").hidden = !state.clubs.size && !state.nats.size;
  for (const input of box.querySelectorAll(".who-input")) if (!$(`#${input.dataset.kind}-menu`).hidden) renderWhoMenu(input);
}
function whoChanged() {
  renderWhoFilter();
  renderTable();
  renderTableFilters();
}
// The list under a box. Empty box: clubs by league (each league opens its clubs) or every
// nationality. Typing: whatever has the text anywhere in its name, starts of names first.
const WHO_MAX = 60;
function whoMatches(items, q) {
  const rank = (k) => k.startsWith(q) ? 0 : k.includes(` ${q}`) || k.includes(`-${q}`) ? 1 : 2;
  return items.filter((x) => x.key.includes(q)).map((x) => [rank(x.key), x])
    .sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name)).slice(0, WHO_MAX).map(([, x]) => x);
}
function renderWhoMenu(input) {
  const kind = input.dataset.kind, menu = $(`#${kind}-menu`);
  const q = whoKey(input.value.trim());
  const { clubs, leagues, nats } = whoOptions();
  const opt = (attrs, on, inner) => `<button type="button" class="who-opt" role="option" tabindex="-1" ${attrs}
    aria-selected="${on}"><span class="tick" aria-hidden="true">${on ? "✓" : ""}</span>${inner}</button>`;
  const clubOpt = (c, sub) => opt(`data-club="${c.id}"`, state.clubs.has(c.id),
    `${clubCrest(c.id, "club-logo")}<span class="nm">${escapeHtml(c.name)}</span>${sub ? `<span class="sub">${escapeHtml(sub)}</span>` : ""}`);
  const natOpt = (n) => opt(`data-nat="${escapeHtml(n.name)}"`, state.nats.has(n.name),
    `${flagImg(n.name)}<span class="nm">${escapeHtml(n.name)}</span>`);
  const lgName = new Map(leagues.map((l) => [l.id, l.name]));
  let html;
  if (kind === "club" && !q) {
    html = leagues.map((l) => {
      const open = state.whoLeague === l.id;
      const country = state.data.competitions[l.id]?.country;
      return `<button type="button" class="who-opt who-league" tabindex="-1" data-league="${l.id}" aria-expanded="${open}">
          <span class="caret" aria-hidden="true">▾</span>${country ? flagImg(countryDisplay(country)) : ""}<span class="nm">${escapeHtml(l.name)}</span><span class="sub">${l.clubs.length}</span></button>`
        + (open ? `<div class="who-clubs">${l.clubs.map((c) => clubOpt(c)).join("")}</div>` : "");
    }).join("");
  } else if (kind === "club") {
    const found = whoMatches(clubs, q);
    html = found.map((c) => clubOpt(c, lgName.get(c.league))).join("") || `<div class="who-empty">No club matches</div>`;
  } else {
    const found = q ? whoMatches(nats, q) : nats;
    html = found.map(natOpt).join("") || `<div class="who-empty">No nationality matches</div>`;
  }
  const active = menu.querySelector(".who-opt.active");
  const keep = active && [...active.attributes].find((a) => /^data-(club|nat|league)$/.test(a.name));
  const top = menu.scrollTop;
  menu.innerHTML = html;
  menu.hidden = false;
  input.setAttribute("aria-expanded", "true");
  if (keep) menu.querySelector(`[${keep.name}="${CSS.escape(keep.value)}"]`)?.classList.add("active");
  menu.scrollTop = top;
}
function closeWhoMenu(input) {
  $(`#${input.dataset.kind}-menu`).hidden = true;
  input.setAttribute("aria-expanded", "false");
}
// Pick or drop a club or nationality, or open or close a league
function whoActivate(input, el) {
  if (el.dataset.league) {
    const id = Number(el.dataset.league);
    state.whoLeague = state.whoLeague === id ? null : id;
    return renderWhoMenu(input);
  }
  const set = el.dataset.club ? state.clubs : state.nats, v = el.dataset.club ? Number(el.dataset.club) : el.dataset.nat;
  if (set.has(v)) set.delete(v); else set.add(v);
  if (input.value) {             // back to the whole list, from the top
    input.value = "";
    menuTop(input);
    el.classList.remove("active");
  }
  whoChanged();       // redraws the open list too
}
const menuTop = (input) => { $(`#${input.dataset.kind}-menu`).scrollTop = 0; };
function whoMove(input, step) {
  const menu = $(`#${input.dataset.kind}-menu`);
  const opts = [...menu.querySelectorAll(".who-opt")];
  if (!opts.length) return;
  const i = opts.findIndex((o) => o.classList.contains("active"));
  const next = opts[i === -1 ? (step > 0 ? 0 : opts.length - 1) : Math.max(0, Math.min(opts.length - 1, i + step))];
  opts.forEach((o) => o.classList.toggle("active", o === next));
  next.scrollIntoView({ block: "nearest" });
}
for (const input of document.querySelectorAll("#who-filter .who-input")) {
  const menu = $(`#${input.dataset.kind}-menu`);
  input.addEventListener("focus", () => renderWhoMenu(input));
  input.addEventListener("input", () => { menuTop(input); renderWhoMenu(input); });
  input.addEventListener("blur", () => closeWhoMenu(input));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (menu.hidden) renderWhoMenu(input);
      whoMove(input, e.key === "ArrowDown" ? 1 : -1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      // the highlighted row, or the best match when typing
      const el = menu.querySelector(".who-opt.active") || (input.value.trim() && menu.querySelector(".who-opt"));
      if (el) whoActivate(input, el);
    } else if (e.key === "Escape" && !menu.hidden) {
      e.preventDefault();
      closeWhoMenu(input);
    }
  });
  // keep the focus in the box, so the list stays open for another pick
  menu.addEventListener("mousedown", (e) => e.preventDefault());
  menu.addEventListener("click", (e) => {
    const el = e.target.closest(".who-opt");
    if (el) whoActivate(input, el);
  });
}
$("#who-filter").addEventListener("click", (e) => {
  if (e.target.closest("[data-who-clear]")) { state.clubs = new Set(); state.nats = new Set(); return whoChanged(); }
  const chip = e.target.closest(".who-chip");
  if (!chip) return;
  if (chip.dataset.club) state.clubs.delete(Number(chip.dataset.club));
  else state.nats.delete(chip.dataset.nat);
  whoChanged();
});
function renderPosFilter() {
  const box = $("#pos-filter");
  box.hidden = state.tableView !== "players" || !state.players;
  if (box.hidden) return;
  const sel = state.positions || new Set();
  const n = {};
  for (const p of state.players.list) for (const r of playsAt(p)) n[r] = (n[r] || 0) + 1;
  box.innerHTML = `<div class="pos-head"><span>Position</span>
      <button type="button" class="pos-clear" data-pos-clear${sel.size ? "" : " hidden"}>Clear</button></div>
    <div class="pitch">${PITCH_LINES}${PITCH_SPOTS.map(([pos, x, y]) =>
      `<button type="button" class="pos" data-pos="${pos}" style="left:${x}%;top:${y}%" aria-pressed="${sel.has(pos)}"
         title="${pos}: ${n[pos] || 0} players">${pos}</button>`).join("")}</div>`;
}
$("#pos-filter").addEventListener("click", (e) => {
  if (e.target.closest("[data-pos-clear]")) state.positions = new Set();
  else {
    const b = e.target.closest("[data-pos]");
    if (!b) return;
    state.positions ||= new Set();
    state.positions.has(b.dataset.pos) ? state.positions.delete(b.dataset.pos) : state.positions.add(b.dataset.pos);
  }
  renderPosFilter();
  renderTable();
  renderTableFilters();
});

// Combine several competitions' stats: counts add up, averages are weighted by what they average over
function mergeStats(parts) {
  if (parts.length < 2) return parts[0] || null;
  const sum = (xs, f) => xs.reduce((a, x) => a + (f(x) || 0), 0);
  const avg = (xs, key, w) => { const n = sum(xs, w); return n ? sum(xs, (x) => x[key] == null ? 0 : x[key] * w(x)) / n : null; };
  const n = sum(parts, (x) => x.n), rated = sum(parts, (x) => x.rated);
  const out = { n, live: sum(parts, (x) => x.live), rated };
  for (const k of ["correct", "exact", "home_rate", "log_loss", "brier", "goal_error"]) out[k] = avg(parts, k, (x) => x.n);
  const mk = parts.map((x) => x.market).filter(Boolean);
  out.market = mk.length ? Object.fromEntries([["n", sum(mk, (m) => m.n)],
    ...["model_ll", "market_ll", "model_correct", "market_correct"].map((k) => [k, avg(mk, k, (m) => m.n)])]) : null;
  out.rating_counts = [0, 1, 2, 3, 4].map((i) => sum(parts, (x) => x.rating_counts?.[i]));
  out.rating_avg = rated ? out.rating_counts.reduce((a, c, i) => a + (i + 1) * c, 0) / rated : null;
  const fa = parts.filter((x) => x.factor_avgs);
  out.factor_avgs = rated ? Object.fromEntries(Object.keys(fa[0].factor_avgs).map((k) =>
    [k, sum(fa, (x) => x.factor_avgs[k] * x.rated) / rated])) : null;
  out.calibration = parts[0].calibration.map((_, i) => {
    const bins = parts.map((x) => x.calibration[i]).filter((b) => b[0]);
    const c = sum(bins, (b) => b[0]);
    return c ? [c, sum(bins, (b) => b[0] * b[1]) / c, sum(bins, (b) => b[0] * b[2]) / c] : [0, null, null];
  });
  const markets = {};
  for (const k of ["1X2", "BTTS", "OU15", "OU25", "OU35", "OU45"]) {
    const ms = parts.map((x) => x.markets?.[k]).filter(Boolean);
    if (!ms.length) continue;
    const open = ms.filter((m) => m.open_n);
    markets[k] = { n: sum(ms, (m) => m.n), model_ll: avg(ms, "model_ll", (m) => m.n), close_ll: avg(ms, "close_ll", (m) => m.n),
      open_n: sum(open, (m) => m.open_n), model_open_ll: avg(open, "model_open_ll", (m) => m.open_n), open_ll: avg(open, "open_ll", (m) => m.open_n) };
  }
  out.markets = Object.keys(markets).length ? markets : null;
  return out;
}

function renderStats() {
  state.drawn.add("stats");
  const body = $("#stats-body");
  const range = state.stats?.ranges?.[state.statsRange];
  const ids = filterLeagueIds(state.statsFilter, statsCountries());
  const s = !range ? null : ids ? mergeStats(ids.map((id) => range[id]).filter(Boolean)) : range.all;
  if (!s) { body.innerHTML = loadFailed("stats") ? loadError("the stats") : `<div class="empty-state">No finished matches with a projection in this range.</div>`; return; }
  const card = (label, value, note = "") =>
    `<div class="stats-card"><div class="stats-label">${label}</div><div class="stats-value">${value}</div>${note ? `<div class="stats-note">${note}</div>` : ""}</div>`;
  const liveNote = s.live === s.n ? "All recorded before kickoff"
    : s.live === 0 ? "Reconstructed from pre-match data"
    : `${s.live.toLocaleString()} recorded before kickoff, rest reconstructed`;
  const rows = s.calibration.map(([count, avgP, hit], i) => {
    if (!count) return "";
    const gap = Math.abs(hit - avgP);
    return `<tr><td>${i * 10}–${i * 10 + 10}%</td><td>${count.toLocaleString()}</td><td>${pct(avgP)}</td>
      <td class="${gap <= 0.03 ? "gap-ok" : gap > 0.06 ? "gap-off" : ""}">${pct(hit)}</td>
      <td style="width:70px"><span class="calib-bar" style="width:${Math.round(hit * 60)}px"></span></td></tr>`;
  }).join("");
  const rc = s.rating_counts || [0, 0, 0, 0, 0];
  const rated = rc.reduce((a, b) => a + b, 0);
  const avgTier = s.rating_avg ? Math.round(s.rating_avg) : null;
  const colours = { 5: "#f6c945", 4: "var(--status-good)", 3: "#c4df00", 2: "var(--series-orange)", 1: "var(--status-critical)" };
  const dist = [5, 4, 3, 2, 1].map((r) => {
    const share = rated ? rc[r - 1] / rated : 0;
    return `<div class="dist-row"><span class="dist-label">${r} ${RATING_LABELS[r]}</span>
      <span class="dist-bar-wrap"><span class="dist-bar" style="display:block;width:${(100 * share).toFixed(1)}%;background:${colours[r]}"></span></span>
      <span class="dist-pct">${pct(share, 0)}</span></div>`;
  }).join("");
  const factorRows = s.factor_avgs ? FACTORS.map(([k, label, w]) => {
    const v = s.factor_avgs[k.slice(2)];
    return `<div class="dist-row"><span class="dist-label">${label} <span class="factor-weight">${w}</span></span>
      <span class="dist-bar-wrap"><span class="dist-bar" style="display:block;width:${(v / 5 * 100).toFixed(1)}%;background:var(--series-blue)"></span></span>
      <span class="dist-pct">${v.toFixed(2)}</span></div>`;
  }).join("") : "";
  const ratingBlock = rated ? `
    <div class="stats-card" style="margin-top:12px">
      <div class="stats-label">Average rating</div>
      <div class="stats-value">${s.rating_avg.toFixed(2)}<span style="font-size:14px;color:var(--text-muted)"> / 5 · ${RATING_LABELS[avgTier]}</span></div>
      <div style="margin-top:10px">${dist}</div>
      <div class="stats-label" style="margin-top:12px">Average by factor (0–5)</div>
      <div style="margin-top:4px">${factorRows}</div>
      <div class="stats-note">Each result is rated 1 (terrible) to 5 (excellent) from five factors, weighted as shown. Tap a result on the Matches tab to see its breakdown.</div>
    </div>` : "";
  const mk = s.market;
  const cmp = (a, b, lowerBetter) => (lowerBetter ? a < b : a > b) ? " better" : "";
  const marketBlock = mk ? `
    <div class="stats-card" style="margin-bottom:12px">
      <div class="stats-label">Model vs Market (${mk.n.toLocaleString()} matches with odds)</div>
      <div class="vs-market">
        <span></span><span class="hd">Model</span><span class="hd">Market fair</span>
        <span>Right result</span><span class="num${cmp(mk.model_correct, mk.market_correct)}">${pct(mk.model_correct)}</span><span class="num${cmp(mk.market_correct, mk.model_correct)}">${pct(mk.market_correct)}</span>
        <span>Log loss</span><span class="num${cmp(mk.model_ll, mk.market_ll, true)}">${mk.model_ll.toFixed(3)}</span><span class="num${cmp(mk.market_ll, mk.model_ll, true)}">${mk.market_ll.toFixed(3)}</span>
      </div>
      <div class="stats-note">Market fair probability: the average across bookmakers with their margin removed, from the last odds before kickoff. Only matches with odds are compared${mk.n < 1000 ? "; the sample is still small, so treat this as a rough guide" : ""}.</div>
    </div>${marketsTable(s.markets)}` : `<div class="stats-card" style="margin-bottom:12px"><div class="stats-label">Model vs Market</div><div class="stats-note">No finished matches with bookmaker odds in this range yet. Odds are collected nightly for upcoming matches.</div></div>`;
  body.innerHTML = `
    <div class="stats-grid">
      ${card("Matches", s.n.toLocaleString(), liveNote)}
      ${card("Right result", pct(s.correct), `Picking the home team every time: ${pct(s.home_rate)}`)}
      ${card("Exact score", pct(s.exact), "Most likely scoreline was spot on")}
      ${card("Goal error", s.goal_error.toFixed(2), "Average goals off per team")}
      ${card("Log loss", s.log_loss.toFixed(3), "Lower is better. Guessing ≈ 1.07")}
      ${card("Brier score", s.brier.toFixed(3), "Lower is better. Guessing ≈ 0.64")}
    </div>` + marketBlock + `
    <div class="stats-card">
      <div class="stats-label">Calibration: when it says X%, how often did it happen?</div>
      <table class="calib-table">
        <thead><tr><th>Said</th><th>Calls</th><th>Avg said</th><th>Happened</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="stats-note">Every home win, draw and away win chance counts as one call. Well calibrated means "Happened" is close to "Avg said".</div>
    </div>` + ratingBlock;
}

// Model vs Market in every bet market: log loss on the same matches against the closing
// prices, and against opening prices where the odds were first seen before kickoff
function marketsTable(ms) {
  if (!ms) return "";
  const keys = ["1X2", "BTTS", "OU15", "OU25", "OU35", "OU45"].filter((k) => ms[k]);
  const gap = (model, book) => {
    const d = model - book;
    return `<span class="${d < 0 ? "pos" : d > 0 ? "neg" : ""}">${d > 0 ? "+" : ""}${d.toFixed(3)}</span>`;
  };
  const rows = keys.map((k) => { const m = ms[k]; return `<tr><td>${MARKET_LABELS[k]}</td><td>${m.n.toLocaleString()}</td>
    <td>${m.model_ll.toFixed(3)}</td><td>${m.close_ll.toFixed(3)}</td><td>${gap(m.model_ll, m.close_ll)}</td>
    <td>${m.open_n ? `${gap(m.model_open_ll, m.open_ll)} <span class="dim">(${m.open_n.toLocaleString()})</span>` : `<span class="dim">–</span>`}</td></tr>`; }).join("");
  return `<div class="stats-card" style="margin-bottom:12px">
      <div class="stats-label">Every bet market: Model vs Market</div>
      <table class="calib-table"><thead><tr><th>Market</th><th>Matches</th><th>Model</th><th>Market fair</th><th>Gap</th><th>Gap at opening</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="stats-note">Log loss, lower is better, on the same matches. Gap = model minus market: green means the model was more accurate. "At opening" compares with the first prices seen, only for matches whose odds were collected before kickoff (count in brackets). Beating the opening price over many matches would be the first sign the model adds something the market lacks; a small or short-lived gap proves nothing. The goal lines come from the model's projected goals.</div>
    </div>`;
}

// ------------------------------------------------------------------ line-up record
// Every XI the model predicted before the team sheet came out, checked against the one that
// started (data/lineups.json, one row per team line-up), or the reconstructed history: the model
// re-run on every past match (data/lineups_history.json, kept apart). Totalled here, so the
// competition menu and the range re-cut everything; each file loads the first time it's shown
const LR_LINES = ["Goalkeeper", "Defence", "Midfield", "Attack"];
const LR_HORIZONS = [["Under 1 hour", 0, 1], ["1–6 hours", 1, 6], ["6–24 hours", 6, 24], ["24 hours or more", 24, Infinity]];
const LR_PAGE = 50;     // line-ups listed per "Show more"
const LR_CLUB_MIN = 3;  // line-ups a club needs for the easiest/hardest lists
const LR_FILES = { live: ["lineupRec", "data/lineups.json"], history: ["lineupHist", "data/lineups_history.json"] };
function loadLineupRecord() {
  const [key, url] = LR_FILES[state.lineupSource];
  if (state[key] !== undefined) return;
  state[key] = null;
  getJsonOrNull(url).then((d) => {
    if (d) d.rows = d.rows.map((r) => {
      const o = Object.fromEntries(d.fields.map((k, i) => [k, r[i]]));
      o.time = Date.parse(o.kickoff.length === 10 ? `${o.kickoff}T12:00:00` : o.kickoff);   // history has the date only
      return o;
    });
    state[key] = d || false;
    renderLineupFilters();
    renderLineupRecord();
  });
}
const lineupData = () => state[LR_FILES[state.lineupSource][0]];
const lrTeam = (id) => state.data.teams[id] || lineupData()?.teams?.[id] || `Team ${id}`;
const lrPlayer = (id) => lineupData()?.players?.[id] || `Player ${id}`;
function lineupCountries() {
  return state.lineupCountries[state.lineupSource] ||= compCountries((lineupData()?.rows || []).map((r) => r.league));
}
// Line-ups in the chosen range, before the competition menu
function lineupScope() {
  const days = state.lineupRange === "all" ? null : Number(state.lineupRange);
  const since = days ? Date.now() - days * 864e5 : -Infinity;
  return (lineupData()?.rows || []).filter((r) => r.time >= since);
}
function renderLineupFilters() {
  if (!lineupData()) { $("#lineup-filters").innerHTML = ""; return; }
  const countries = lineupCountries(), scope = lineupScope();
  const countOf = (value) => {
    const ids = filterLeagueIds(value, countries);
    return ids ? scope.filter((r) => ids.includes(r.league)).length : scope.length;
  };
  renderFilterMenu($("#lineup-filters"), state.lineupFilter, countries, countOf, {
    all: "All competitions", country: (c) => `All ${c} line-ups`, region: (r) => `All line-ups in ${r}`,
    euro: "Champions League, Europa League and Conference League line-ups", cup: (name) => `${name} line-ups`,
  });
}
function lineupTotals(list) {
  const n = list.length, correct = list.reduce((a, r) => a + r.correct, 0);
  return {
    n, correct, starters: 11 * n, mean: n ? correct / n : 0,
    perfect: list.filter((r) => r.correct === 11).length,
    rolesRight: list.reduce((a, r) => a + r.roles_right, 0), rolesKnown: list.reduce((a, r) => a + r.roles_known, 0),
    matches: new Set(list.map((r) => r.fixture)).size,
  };
}
function lineupGroups(list, key) {
  const groups = new Map();
  for (const r of list) {
    const k = key(r);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  }
  return [...groups.entries()].map(([k, g]) => [k, g, lineupTotals(g)]);
}
const lrOf11 = (x) => `${x.toFixed(1)} of 11`;
const lrShare = (a, b) => b ? pct(a / b) : "–";
const lrScore = (k) => `<span class="xi-score xi-score-${k >= 9 ? "good" : k >= 7 ? "ok" : "poor"}">${k}/11</span>`;
const lrDate = (t, o = { day: "numeric", month: "short" }) => new Date(t).toLocaleDateString("en-GB", o);
function lrBar(label, value, max, text, tip) {
  return `<div class="dist-row" title="${escapeHtml(tip)}"><span class="dist-label">${label}</span>
    <span class="dist-bar-wrap"><span class="dist-bar" style="display:block;width:${(max ? 100 * value / max : 0).toFixed(1)}%;background:var(--series-blue)"></span></span>
    <span class="dist-pct">${text}</span></div>`;
}
function renderLineupRecord() {
  const body = $("#lineup-body");
  const d = lineupData(), live = state.lineupSource === "live";
  if (d === null || d === undefined) { body.innerHTML = `<div class="empty-state">Loading line-ups…</div>`; return; }
  if (!d || d.available === false) {
    body.innerHTML = loadFailed("lineups", "lineups_history") ? loadError("the line-up record") : `<div class="empty-state">The ${live ? "line-up record" : "reconstructed history"} is built by the nightly data run. Check back tomorrow.</div>`;
    return;
  }
  const ids = filterLeagueIds(state.lineupFilter, lineupCountries());
  const list = lineupScope().filter((r) => !ids || ids.includes(r.league));
  if (!list.length) {
    body.innerHTML = `<div class="empty-state">${d.rows.length ? "No scored line-ups in this range."
      : "No line-ups scored yet. Each needs a prediction saved before the team sheet came out, and the official XI afterwards."}</div>`;
    return;
  }
  const t = lineupTotals(list);
  const card = (label, value, note = "") =>
    `<div class="stats-card"><div class="stats-label">${label}</div><div class="stats-value">${value}</div>${note ? `<div class="stats-note">${note}</div>` : ""}</div>`;
  const section = (label, html, note = "") =>
    `<div class="stats-card"><div class="stats-label">${label}</div>${html}${note ? `<div class="stats-note">${note}</div>` : ""}</div>`;
  const table = (head, rows, cls = "") =>
    `<table class="calib-table ${cls}"><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
  const sample = t.n < 200 ? `Very early: ${t.n.toLocaleString()} line-ups is too few to judge the model, so these figures will move a lot.`
    : t.n < 1000 ? `Still a small sample (${t.n.toLocaleString()} line-ups): small differences are likely to be luck.` : "";

  // how many of the 11 each line-up got
  const counts = Array(12).fill(0);
  for (const r of list) counts[r.correct] += 1;
  const lo = Math.min(6, ...list.map((r) => r.correct)), top = Math.max(...counts);
  const spread = [];
  for (let k = 11; k >= lo; k--) spread.push(lrBar(`${k} of 11`, counts[k], top, `${counts[k]} · ${lrShare(counts[k], t.n)}`,
    `${k} of 11 right: ${counts[k]} line-ups`));

  // average per day; per week past four weeks, per month past six months
  const span = list[list.length - 1].time - list[0].time;
  const step = span > 183 * 864e5 ? "month" : span > 28 * 864e5 ? "week" : "day";
  const years = new Date(list[0].time).getFullYear() !== new Date(list[list.length - 1].time).getFullYear();
  const dateOf = (t) => lrDate(t, years ? { day: "numeric", month: "short", year: "numeric" } : undefined);
  const dayKey = (r) => {
    const x = new Date(r.time);
    x.setHours(0, 0, 0, 0);
    if (step === "week") x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
    if (step === "month") x.setDate(1);
    return x.getTime();
  };
  const trend = lineupGroups(list, dayKey).sort((a, b) => b[0] - a[0]).map(([k, , g]) => {
    const label = step === "month" ? lrDate(k, { month: "short", year: "numeric" })
      : `${step === "week" ? "w/c " : ""}${lrDate(k, { weekday: "short", day: "numeric", month: "short", ...(years ? { year: "2-digit" } : {}) })}`;
    return lrBar(label, g.mean, 11, `${g.mean.toFixed(1)} <span class="dim">(${g.n})</span>`,
      `${label}: ${lrOf11(g.mean)} from ${g.n} line-ups, ${g.perfect} perfect`);
  });

  const lines = LR_LINES.map((name, i) => {
    const starters = list.reduce((a, r) => a + r.lines[2 * i], 0), hit = list.reduce((a, r) => a + r.lines[2 * i + 1], 0);
    return `<tr><td>${name}</td><td>${starters.toLocaleString()}</td><td>${hit.toLocaleString()}</td><td>${lrShare(hit, starters)}</td>
      <td style="width:70px"><span class="calib-bar" style="width:${Math.round((starters ? hit / starters : 0) * 60)}px"></span></td></tr>`;
  });
  const timing = LR_HORIZONS.map(([label, a, b]) => {
    const g = lineupTotals(list.filter((r) => r.hours_before >= a && r.hours_before < b));
    return `<tr><td>${label}</td><td>${g.n}</td><td>${g.n ? lrOf11(g.mean) : "–"}</td><td>${lrShare(g.perfect, g.n)}</td></tr>`;
  });
  const comps = lineupGroups(list, (r) => r.league).sort((a, b) => b[2].n - a[2].n || b[2].mean - a[2].mean).map(([id, , g]) =>
    `<tr data-league="${id}"${String(id) === state.lineupFilter ? ` style="font-weight:700"` : ""}><td>${escapeHtml(compLabel(id))}</td>
      <td>${g.n}</td><td>${lrOf11(g.mean)}</td><td>${lrShare(g.perfect, g.n)}</td><td>${lrShare(g.rolesRight, g.rolesKnown)}</td></tr>`);

  const clubRow = ([id, , g]) => `<tr><td>${clubLink(id, lrTeam(id))}</td><td>${g.n}</td><td>${lrOf11(g.mean)}</td><td>${lrShare(g.perfect, g.n)}</td></tr>`;
  const clubHead = ["Club", "Line-ups", "Named", "Perfect"];
  const clubs = lineupGroups(list, (r) => r.team);
  const ranked = clubs.filter(([, , g]) => g.n >= LR_CLUB_MIN).sort((a, b) => b[2].mean - a[2].mean || b[2].n - a[2].n);
  const k = Math.min(10, Math.floor(ranked.length / 2));
  const clubHtml = (k >= 3
    ? `<div class="stats-label" style="margin-top:8px">Easiest to predict</div>${table(clubHead, ranked.slice(0, k).map(clubRow))}
       <div class="stats-label" style="margin-top:12px">Hardest to predict</div>${table(clubHead, ranked.slice(-k).reverse().map(clubRow))}`
    : `<div class="stats-note">The easiest and hardest clubs are listed once enough clubs have ${LR_CLUB_MIN} or more line-ups scored.</div>`)
    + `<details><summary>All ${clubs.length} clubs</summary>${table(clubHead,
      [...clubs].sort((a, b) => lrTeam(a[0]).localeCompare(lrTeam(b[0]))).map(clubRow))}</details>`;

  const tally = (field) => {
    const c = new Map();
    for (const r of list) for (const p of r[field]) {
      const x = c.get(p) || { n: 0, team: r.team };
      x.n += 1;
      c.set(p, x);
    }
    return [...c.entries()].filter(([, x]) => x.n >= 2)
      .sort((a, b) => b[1].n - a[1].n || lrPlayer(a[0]).localeCompare(lrPlayer(b[0]))).slice(0, 15);
  };
  const playerTable = (label, items) => `<div class="stats-label" style="margin-top:10px">${label}</div>` + (items.length
    ? table(["Player", "Club", "Times"], items.map(([p, x]) => `<tr><td>${playerLink(p, lrPlayer(p))}</td><td>${escapeHtml(lrTeam(x.team))}</td><td>${x.n}</td></tr>`))
    : `<div class="stats-note">No player more than once yet.</div>`);
  const missedTotal = list.reduce((a, r) => a + r.missed.length, 0);

  const versions = !live ? [] : lineupGroups(list, (r) => r.version).sort((a, b) => a[0] - b[0]).map(([i, , g]) => {
    const v = d.versions[i] || {};
    return `<tr><td>v${i + 1} <span class="lr-sub">${escapeHtml(v.name || "unknown")}${v.registered ? ` · from ${lrDate(v.registered, { day: "numeric", month: "short", year: "numeric" })}` : ""}</span></td>
      <td>${g.n}</td><td>${lrOf11(g.mean)}</td><td>${lrShare(g.perfect, g.n)}</td></tr>`;
  });

  const newest = [...list].reverse(), shown = newest.slice(0, state.lineupShown);
  const every = shown.map((r) => `<tr><td>${dateOf(r.time)}</td>
    <td>${clubLink(r.team, lrTeam(r.team))} ${r.home ? "v" : "at"} ${escapeHtml(lrTeam(r.opponent))}<span class="lr-sub">${escapeHtml(compLabel(r.league))}</span></td>
    <td>${lrScore(r.correct)}</td><td>${r.missed.length ? r.missed.map((p) => escapeHtml(lrPlayer(p))).join(", ") : "–"}</td></tr>`);
  const more = newest.length > shown.length
    ? `<button type="button" class="filter-chip lr-more" data-more>Show more (${(newest.length - shown.length).toLocaleString()} left)</button>` : "";

  const about = live ? "" : `<div class="stats-card" style="margin-bottom:12px"><div class="stats-note">
    <b>Reconstructed, not a live record.</b> Today's model re-run on every past match, picking from what it knew before
    kick-off: the last five matches' minutes and formations, and the injury list. It can't know late team news, and older
    matches were never predicted this way at the time, so read it as how the current model does on past matches.
    The live record (Saved before kick-off) is the one that counts.</div></div>`;
  body.innerHTML = about + `
    <div class="stats-grid">
      ${card("Line-ups", t.n.toLocaleString(), `From ${t.matches.toLocaleString()} matches, ${dateOf(list[0].time)} to ${dateOf(list[list.length - 1].time)}`)}
      ${card("Named correctly", lrOf11(t.mean), `${t.correct.toLocaleString()} of ${t.starters.toLocaleString()} starters (${lrShare(t.correct, t.starters)})`)}
      ${card("Perfect XIs", t.perfect.toLocaleString(), `All 11 right in ${lrShare(t.perfect, t.n)} of line-ups`)}
      ${card("Right position", lrShare(t.rolesRight, t.rolesKnown), "Correct starters also put where they played")}
    </div>`
    + (sample ? `<div class="stats-card" style="margin-bottom:12px"><div class="stats-note">${sample}</div></div>` : "")
    + section("Starters named correctly, per line-up", `<div style="margin-top:6px">${spread.join("")}</div>`,
      "Number of team line-ups, and their share, by how many of the 11 starters the predicted XI named.")
    + section(`Over time: average named correctly each ${step}`, `<div style="margin-top:6px">${trend.join("")}</div>`,
      "Out of 11, newest first; the number of line-ups is in brackets.")
    + section("By position", table(["Line", "Starters", "Predicted", "Hit rate", ""], lines),
      "Of the players who started in each part of the pitch, how many were in the predicted XI. Lines come from the team sheet.")
    + (live ? section("How far before kick-off", table(["Saved", "Line-ups", "Named", "Perfect"], timing),
      "The prediction scored is the last one saved before the team sheet came out.") : "")
    + section("By competition", table(["Competition", "Line-ups", "Named", "Perfect", "Position"], comps), "Tap a competition to narrow to it.")
    + section("By club", clubHtml, `Clubs with at least ${LR_CLUB_MIN} line-ups scored in the easiest and hardest lists.`)
    + section("Players the model got wrong most often", playerTable("Started, but not in the predicted XI", tally("missed"))
      + playerTable("In the predicted XI, but didn't start", tally("wrong")),
      `${missedTotal.toLocaleString()} starters missed in all; each miss is one wrong pick in their place.`)
    + (live ? section("By model version", table(["Version", "Line-ups", "Named", "Perfect"], versions),
      "A new version starts whenever the line-up code changes, even if the name stays the same. Each keeps its own record.") : "")
    + section("Every line-up", table(["Date", "Line-up", "Right", "Missed"], every, "lr-list") + more,
      `Newest first.${live ? " A match's Line-ups on the Matches tab shows the XIs side by side for the last three weeks." : ""}${d.excluded_no_official_xi ? ` ${d.excluded_no_official_xi} line-ups aren't counted because no complete official XI was recorded.` : ""}`);
}

// ------------------------------------------------------------------ bets
const MARKET_LABELS = { "1X2": "Result", OU15: "Over/Under 1.5", OU25: "Over/Under 2.5", OU35: "Over/Under 3.5", OU45: "Over/Under 4.5", BTTS: "Both teams score" };
const SEL_LABELS = { Home: "Home win", Draw: "Draw", Away: "Away win", Yes: "Both score", No: "Not both score" };

// Paper money: every bet is a flat £ stake out of a starting bank (rules in bets.json)
const betStake = () => state.bets?.rules?.stake_gbp ?? 10;
const betBank = () => state.bets?.rules?.bank ?? 1000;
function gbp(x, sign = false) {
  if (x == null) return "–";
  const v = `£${Math.abs(x).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (!sign) return (x < 0 ? "−" : "") + v;
  return `<span class="${x > 0 ? "pos" : x < 0 ? "neg" : ""}">${x > 0 ? "+" : x < 0 ? "−" : ""}${v}</span>`;
}

function summarise(bets) {
  const stake = betStake();
  const settled = bets.filter((b) => b.result === "win" || b.result === "loss");
  const clvs = settled.map((b) => b.clv).filter((c) => c != null);
  const profit = stake * settled.reduce((a, b) => a + b.profit, 0);
  const staked = stake * settled.length;
  const pending = bets.filter((b) => !b.result).length;
  return {
    placed: bets.length, settled: settled.length, pending, atRisk: stake * pending,
    wins: settled.filter((b) => b.result === "win").length, profit, staked,
    roi: staked ? profit / staked : null,
    beat: clvs.length ? clvs.filter((c) => c > 0).length / clvs.length : null,
  };
}

// A paper bet's model probability, market fair probability and the difference, in whole points,
// as they were when it was taken (the match card's bars show the latest prices)
function betProbs(b) {
  const model = Math.round(100 * b.model_prob), fair = b.fair_prob != null ? Math.round(100 * b.fair_prob) : null;
  const diff = fair == null ? "" : ` · difference ${model >= fair ? "+" : "−"}${Math.abs(model - fair)} pts`;
  return `When taken: model ${model}% · market fair ${fair == null ? "–" : `${fair}%`}${diff}`;
}

function signed(x, d = 1, suffix = "") {
  if (x == null) return "–";
  const cls = x > 0 ? "pos" : x < 0 ? "neg" : "";
  return `<span class="${cls}">${x > 0 ? "+" : ""}${x.toFixed(d)}${suffix}</span>`;
}

// On both betting tabs, above the numbers: age, what the bets are for, and where to get help
const GAMBLING_NOTE = `<div class="sim-banner gamble-note"><span class="age-18" title="For over-18s only">18+</span>
  Paper bets for testing the model, not betting advice. If gambling is causing you problems, free confidential help is at
  <a href="https://www.begambleaware.org/" rel="noopener">BeGambleAware.org</a>.</div>`;
function renderBets() {
  state.drawn.add("bets");
  const body = $("#bets-body");
  if (!state.bets) { body.innerHTML = GAMBLING_NOTE + (loadFailed("bets") ? loadError("the paper bets") : `<div class="empty-state">No simulated paper bets yet.</div>`); return; }
  const stake = betStake(), bank = betBank();
  const scope = betScope();
  const ids = filterLeagueIds(state.betFilter, betCountries());
  const all = ids ? scope.filter((b) => ids.includes(b.league)) : scope;
  const s = summarise(all);
  const card = (label, value, note = "") =>
    `<div class="stats-card"><div class="stats-label">${label}</div><div class="stats-value">${value}</div>${note ? `<div class="stats-note">${note}</div>` : ""}</div>`;
  const rules = state.bets.rules;
  const tableRow = (label, x, attr = "") => `<tr${attr}><td>${label}</td><td>${x.settled}${x.pending ? ` <span class="dim">+${x.pending}</span>` : ""}</td>
    <td>${x.settled ? `${x.wins}/${x.settled}` : "–"}</td><td>${x.settled ? gbp(x.profit, true) : "–"}</td>
    <td>${x.roi == null ? "–" : signed(100 * x.roi, 1, "%")}</td></tr>`;
  const head = (first) => `<thead><tr><th>${first}</th><th>Bets</th><th>Won</th><th>Profit</th><th>Return</th></tr></thead>`;
  // By league within the filters above; tap one to narrow to it
  const byLeague = {};
  for (const b of all) (byLeague[b.league] = byLeague[b.league] || []).push(b);
  const leagueRows = Object.entries(byLeague).map(([id, bs]) => [id, summarise(bs)])
    .sort((a, b) => b[1].settled - a[1].settled || b[1].placed - a[1].placed)
    .map(([id, x]) => tableRow(escapeHtml(compLabel(id)), x,
      ` data-league="${id}" style="cursor:pointer${id === state.betFilter ? ";font-weight:700" : ""}"`)).join("");
  const marketRows = ["1X2", "OU15", "OU25", "OU35", "OU45", "BTTS"].map((mk) => {
    const x = summarise(all.filter((b) => b.market === mk));
    return x.placed ? tableRow(MARKET_LABELS[mk], x) : "";
  }).join("");
  // Bank after each settled bet, oldest first, on the filters above
  const settled = all.filter((b) => b.result).sort((a, b) => new Date(a.kickoff) - new Date(b.kickoff) || a.id - b.id);
  const bankAfter = {};
  let running = bank;
  for (const b of settled) { running += stake * (b.profit || 0); bankAfter[b.id] = running; }
  settled.reverse();
  const row = (b) => {
    const res = b.result === "win" ? `<span class="pos">Won +${gbp(stake * b.profit)}</span>`
      : b.result === "loss" ? `<span class="neg">Lost −${gbp(stake)}</span>`
      : b.result === "void" ? "Void, stake back" : `<span class="dim">To win ${gbp(stake * (b.odds - 1))}</span>`;
    return `<div class="bet-row ${["win", "loss", "void"].includes(b.result) ? b.result : ""}">
      <div class="bet-top"><span>${escapeHtml(fmtDay(b.kickoff))} ${escapeHtml(fmtTime(b.kickoff))} · ${escapeHtml(compLabel(b.league))}</span><span>${b.strategy === "early" ? "Night before" : "Pre-kickoff"}</span></div>
      <div class="bet-match">${escapeHtml(b.home)} v ${escapeHtml(b.away)}${b.score ? ` <span style="color:var(--text-muted)">(${escapeHtml(b.score)})</span>` : ""}</div>
      <div class="bet-pick"><span>${betBadges(b)}${gbp(stake)} on ${escapeHtml(SEL_LABELS[b.selection] || b.selection)} @ <b>${b.odds.toFixed(2)}</b> <span style="color:var(--text-muted);font-size:11px">${escapeHtml(b.bookmaker || "")}</span></span><span>${res}</span></div>
      <div class="bet-sub">${betProbs(b)}${b.closing_odds != null ? ` · closed ${b.closing_odds.toFixed(2)}` : ""}${bankAfter[b.id] != null ? ` · simulated bank ${gbp(bankAfter[b.id])}` : ""}</div>
    </div>`;
  };
  body.innerHTML = `
    ${GAMBLING_NOTE}
    <div class="sim-banner">Simulated: paper bets only, no real money staked. Every figure here is a simulation at recorded prices.</div>
    <div class="stats-grid">
      ${card("Simulated bank", gbp(bank + s.profit), `Started with ${gbp(bank)}${s.pending ? ` · ${gbp(s.atRisk)} on ${s.pending} pending` : ""}`)}
      ${card("Simulated profit", s.settled ? gbp(s.profit, true) : "–", s.staked ? `${gbp(s.staked)} staked · return ${(s.roi > 0 ? "+" : "") + (100 * s.roi).toFixed(1)}%` : `${gbp(stake)} on every bet`)}
      ${card("Won", s.settled ? `${s.wins}<span style="font-size:14px;color:var(--text-muted)"> of ${s.settled}</span>` : "–", s.settled ? `${pct(s.wins / s.settled)} of settled bets` : "Needs settled bets")}
      ${card("Beat the closing price", s.beat == null ? "–" : pct(s.beat), "Took better odds than the last price before kickoff. Only means something over a large sample, and is not proof of value on its own")}
    </div>
    ${leagueRows ? `<div class="stats-card" style="margin-bottom:12px">
      <div class="stats-label">By league</div>
      <table class="calib-table">${head("League")}<tbody>${leagueRows}</tbody></table>
      <div class="stats-note">Tap a league to see only its bets (tap again for all). Bets = settled <span class="dim">+ pending</span>. For how accurate the predictions are in a league, pick it on the Stats tab.</div>
    </div>` : ""}
    ${marketRows ? `<div class="stats-card" style="margin-bottom:12px">
      <div class="stats-label">By market</div>
      <table class="calib-table">${head("Market")}<tbody>${marketRows}</tbody></table>
      <div class="stats-note">Paper bets, no real money: ${gbp(stake)} on every bet from a ${gbp(bank)} bank. A match gets at most one bet of each kind (result, goal line, both teams score): of several, the best is kept, judged as if the true chance were halfway between the model's and the bookmakers'. If both the night-before and pre-kickoff runs bet the same kind on a match, All counts only the night-before bet. All bets are simulated at ${escapeHtml(rules.bookmaker || "Bet365")}'s recorded odds. A paper bet is taken when the model's probability × that price is at least ${Math.round(rules.min_edge * 100)}% better than even, at odds up to ${rules.max_odds}: a disagreement with the market, which the results below test rather than assume. Return = profit ÷ staked. Profit needs a few hundred settled bets before it means much.</div>
    </div>` : ""}
    ${settled.length ? `<div class="modal-section">Settled (${settled.length})</div><div class="bets-list">${settled.slice(0, 300).map(row).join("")}</div>` : ""}
    ${!all.length ? `<div class="empty-state">No bets match this filter yet.</div>` : ""}
    ${s.pending ? `<div class="stats-note" style="margin-top:12px">${s.pending} paper bet${s.pending === 1 ? "" : "s"} still to be played: see Model vs Market.</div>` : ""}`;
}

// ---- Model vs Market: the paper simulation's open selections (where the model and the market
// disagree enough for it to take one), one per pick, soonest first, grouped by day
function tipLabel(b) {
  if (b.market === "1X2") return b.selection === "Draw" ? "Draw" : `${b.selection === "Home" ? b.home : b.away} to win`;
  if (b.market === "BTTS") return b.selection === "Yes" ? "Both teams to score: Yes" : "Both teams to score: No";
  return `${b.selection} goals`;
}
// How the model has done against the market, red where it's behind: accuracy on every market
// with odds (Stats, last 12 months), and the settled paper selections' closing-price record and
// simulated profit
function tipsOverview() {
  // one panel of figures: a status pill (green ahead, red behind, grey no data yet), the figure,
  // then label-value rows
  const tile = (ok, pill, label, value, rows, title = "") =>
    `<div class="kpi"${title ? ` title="${title}"` : ""}><div class="kpi-head"><span class="stats-label">${label}</span><span class="kpi-pill ${ok == null ? "" : ok ? "good" : "bad"}">${pill}</span></div>
      <div class="kpi-value">${value}</div>
      <div class="kpi-rows">${rows.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("")}</div></div>`;
  const tiles = [];
  const st = state.stats?.ranges?.["365d"]?.all;
  const ms = Object.values(st?.markets || {});
  if (ms.length) {
    const better = ms.filter((m) => m.model_ll < m.close_ll).length;
    const n = Math.max(...ms.map((m) => m.n));
    const ahead = better > ms.length / 2;
    tiles.push(tile(ahead, ahead ? "Ahead" : "Behind", "Model vs Market", `${better}<small>of ${ms.length} markets</small>`,
      [["Matches with odds", n.toLocaleString()],
       ...(st.market ? [["Right result, model", pct(st.market.model_correct)], ["Right result, market", pct(st.market.market_correct)]] : [])],
      "Bet markets where the model's log loss beat the closing market fair price, last 12 months"));
  }
  const settled = onePerPick(state.bets?.bets || []).filter((b) => b.result === "win" || b.result === "loss");
  const s = summarise(settled);
  tiles.push(tile(s.beat == null ? null : s.beat >= 0.5, s.beat == null ? "No data" : s.beat >= 0.5 ? "Above 50%" : "Below 50%",
    "Beat closing price", s.beat == null ? "–" : pct(s.beat),
    [["Settled selections", s.settled || "0"], ["Target", "Over 50%"]],
    "Share of paper selections taken at better odds than the last price before kickoff. Staying above 50% over a large sample would suggest real mispricing; it is not proof on its own"));
  tiles.push(tile(s.settled ? s.profit >= 0 : null, s.settled ? `${s.roi > 0 ? "+" : ""}${(100 * s.roi).toFixed(1)}% return` : "No data",
    "Simulated profit", s.settled ? `${s.profit >= 0 ? "+" : "−"}${gbp(Math.abs(s.profit))}` : "–",
    [["Won", s.settled ? `${s.wins} of ${s.settled}` : "–"], ["Strike rate", s.settled ? pct(s.wins / s.settled) : "–"]]));
  return `<div class="tips-overview">${tiles.join("")}</div>`;
}

// The paper bank box: the viewer's simulated bank and stake size, kept in this browser only.
// With no bank entered the selections show the simulation's flat stake.
const readStored = (k) => { try { return localStorage.getItem(`fc.${k}`); } catch { return null; } };
const writeStored = (k, v) => { try { v == null ? localStorage.removeItem(`fc.${k}`) : localStorage.setItem(`fc.${k}`, v); } catch { /* not stored */ } };
function tipStake() {
  const bal = parseFloat($("#tips-balance").value), frac = parseFloat($("#tips-pct").value);
  if (!(bal > 0)) return { stake: betStake(), bal: null };
  const raw = bal * frac;
  // to the 50p from £5, else to the 10p
  return { stake: raw >= 5 ? Math.round(raw * 2) / 2 : Math.max(0.1, Math.round(raw * 10) / 10), bal };
}
{
  const bal = readStored("balance"), frac = readStored("stakePct");
  if (bal) $("#tips-balance").value = bal;
  if (frac && [...$("#tips-pct").options].some((o) => o.value === frac)) $("#tips-pct").value = frac;
  const changed = () => { writeStored("balance", $("#tips-balance").value || null); writeStored("stakePct", $("#tips-pct").value); if (state.bets) renderTips(); };
  $("#tips-balance").addEventListener("input", changed);
  $("#tips-pct").addEventListener("change", changed);
}

function renderTips() {
  state.drawn.add("tips");
  const body = $("#tips-body");
  const { stake, bal } = tipStake(), book = state.bets?.rules?.bookmaker || "Bet365";
  const now = Date.now();
  const tips = onePerPick(state.bets?.bets || []).filter((b) => !b.result && new Date(b.kickoff) > now)
    .sort((a, b) => new Date(a.kickoff) - new Date(b.kickoff) || a.fixture - b.fixture || a.id - b.id);
  $("#tips-top").innerHTML = GAMBLING_NOTE + tipsOverview();
  $("#tips-stake").textContent = gbp(stake);
  const total = stake * tips.length;
  $("#tips-total").textContent = !tips.length ? "No open selections"
    : `${tips.length} open selection${tips.length === 1 ? "" : "s"}: ${gbp(total)} simulated in total${bal ? ` (${Math.round(100 * total / bal)}% of paper bank)` : ". Enter a paper bank to size it"}`;
  const intro = `<div class="sim-banner">Model probability against market fair probability for the paper simulation's open selections. A difference is a disagreement with the market, not proven value. Simulated ${gbp(stake)} stake each at ${escapeHtml(book)}'s recorded price; no real money. More can appear up to 75 minutes before kickoff, after late team news.</div>`;
  if (!tips.length) { body.innerHTML = intro + (loadFailed("bets") ? loadError("the open selections") : `<div class="empty-state">No open selections right now. New ones are added the night before and shortly before kickoff.</div>`); return; }
  // by day, then competition (the Matches tab's order), then match; days and competitions fold
  const days = [];
  for (const b of tips) {
    const day = fmtDay(b.kickoff);
    if (days.at(-1)?.day !== day) days.push({ day, tips: [] });
    days.at(-1).tips.push(b);
  }
  const orderOf = (id) => { const i = GROUP_ORDER.indexOf(id); return i === -1 ? 999 : i; };
  const folded = state.tipsCollapsed;
  const fold = (key) => `data-fold="${escapeHtml(key)}" role="button" tabindex="0" aria-expanded="${!folded.has(key)}"`;
  const caret = (key) => `<span class="comp-group-caret" aria-hidden="true">${folded.has(key) ? "&#9656;" : "&#9662;"}</span>`;
  const group = (list, key) => { const m = new Map(); for (const b of list) { const k = b[key]; if (!m.has(k)) m.set(k, []); m.get(k).push(b); } return m; };
  // the top of each card is the match as on the Matches tab (badges, ranks, projected and likely
  // score, model and market probabilities), then the selections
  const byId = new Map(state.data.matches.map((m) => [m.id, m]));
  const matchCard = (bs) => {
    const m = byId.get(bs[0].fixture);
    const count = bs.length > 1 ? `<span class="match-meta">${bs.length} selections · ${gbp(stake * bs.length)}</span>` : "";
    const head = m ? matchHead(m, count) + probBars(m)
      : `<div class="bet-top"><span>${escapeHtml(fmtTime(bs[0].kickoff))}</span>${count}</div>
         <div class="bet-match">${escapeHtml(bs[0].home)} v ${escapeHtml(bs[0].away)}</div>`;
    return `<div class="match-card">${head}<div class="tip-picks">
      ${bs.map((b) => `<div class="tip-pick"><span class="tip-left">${betBadges(b)}<span><span class="sel">${escapeHtml(tipLabel(b))}</span><span class="win">${betProbs(b)}</span><span class="win">Simulated ${gbp(stake)} would win ${gbp(stake * (b.odds - 1))}</span></span></span><span class="odds">${b.odds.toFixed(2)}</span></div>`).join("")}
    </div></div>`;
  };
  body.innerHTML = intro + days.map((d) => {
    const comps = group(d.tips, "league");
    const ordered = [...comps.keys()].sort((a, b) => orderOf(a) - orderOf(b) || compLabel(a).localeCompare(compLabel(b)));
    const dk = `d:${d.day}`;
    return `<div class="tip-day" ${fold(dk)}>${caret(dk)}<span>${escapeHtml(d.day)}</span><span class="comp-group-count">${d.tips.length} · ${gbp(stake * d.tips.length)}</span></div>
      <div class="tip-day-body${folded.has(dk) ? " collapsed" : ""}">${ordered.map((id) => {
        const ck = `c:${d.day}|${id}`;
        return `<div class="comp-group${folded.has(ck) ? " collapsed" : ""}">
          <div class="comp-group-header" ${fold(ck)}>${caret(ck)}<span class="comp-group-name">${escapeHtml(compLabel(id))}</span><span class="comp-group-count">${comps.get(id).length}</span></div>
          <div class="card-list">${[...group(comps.get(id), "fixture").values()].map(matchCard).join("")}</div>
        </div>`;
      }).join("")}</div>`;
  }).join("");
}
$("#tips-body").addEventListener("click", (e) => {
  const head = e.target.closest("[data-fold]");
  if (!head) return;
  const key = head.dataset.fold;
  if (!state.tipsCollapsed.delete(key)) state.tipsCollapsed.add(key);
  renderTips();
});

function xiBlock(teamId) {
  const xi = state.players?.nextXi?.[String(teamId)];
  if (!xi || !xi.players.length) return "";
  const m = state.data.matches.find((x) => x.id === xi.fixture);
  const home = m && m.home === teamId;
  const rating = m ? (home ? m.home_xi : m.away_xi) : null;
  const recent = m ? (home ? m.home_recent_xi : m.away_recent_xi) : null;
  const opp = m ? `${home ? "v" : "@"} ${teamName(home ? m.away : m.home)}` : "next match";
  return `<div class="modal-section">Predicted XI, ${escapeHtml(opp)}${rating != null ? ` · rating ${Math.round(rating)}${recent != null ? ` (recent ${Math.round(recent)})` : ""}` : ""}</div>
    ${xi.players.map(([pid, name, pos, rank]) => `<div class="team-row"><span class="team-row-date">${POS_LABEL[pos] || escapeHtml(pos || "")}</span>
      <span class="team-row-opp">${playerLink(pid, name)}</span><span class="team-row-res">${rankChipSmall(rank)}</span></div>`).join("")}`;
}

async function renderMatchLineups(m, panel) {
  const finished = FINISHED.has(m.status) && m.hg != null;
  panel.innerHTML = `<div class="empty-state">Loading ${finished ? "actual line-ups" : "predicted line-ups"}…</div>`;
  const [homeData, awayData] = await Promise.all([loadClub(m.home), loadClub(m.away), loadPlayers()]);
  const exact = (finished ? state.players?.actualXi : state.players?.fixtureXi)?.[String(m.id)] || {};
  if (!finished && (!exact[String(m.home)] || !exact[String(m.away)])) {
    state.injuries ||= await getJsonOrNull("data/injuries.json");
    await seasonsFor(homeData, awayData);
  }
  const side = (teamId, data, home) => {
    const rating = home ? m.home_xi : m.away_xi;
    const recent = home ? m.home_recent_xi : m.away_recent_xi;
    let label = `${teamName(teamId)}${rating != null ? ` · rating ${Math.round(rating)}${recent != null ? ` (recent ${Math.round(recent)})` : ""}` : ""}`;
    const listed = exact[String(teamId)];
    if (listed?.length) {
      const xi = listed.map(([pid, name, pos, rank]) => ({ p: { id: pid, name }, b: { label: pos }, rank, chance: null, mins: null }));
      const predicted = finished ? state.players?.prematchXi?.[String(m.id)]?.[String(teamId)] : null;
      const hits = predicted?.length ? markPredicted(xi, predicted) : null;
      const score = hits == null ? "" : `<span class="xi-score xi-score-${hits >= 9 ? "good" : hits >= 7 ? "ok" : "poor"}" title="Starters the model predicted">${hits}/${xi.length} predicted</span>`;
      return `<div><div class="modal-section xi-head"><span>${escapeHtml(label)}</span>${score}</div>${xiPitch(xi, data, { note: "" })}</div>`;
    }
    if (finished) return `<div><div class="modal-section">${escapeHtml(label)}</div><div class="page-note">No actual line-up for this team.</div></div>`;
    const xi = predictedXi(teamId, data, m);
    if (!xi) return `<div class="modal-section">${escapeHtml(label)}</div><div class="page-note">No predicted XI for this team.</div>`;
    return `<div><div class="modal-section">${escapeHtml(label)}</div>${xiPitch(xi, data, { note: "" })}</div>`;
  };
  const marked = finished && state.players?.prematchXi?.[String(m.id)];
  panel.innerHTML = `<div class="fixture-lineups">${side(m.home, homeData, true)}${side(m.away, awayData, false)}</div>
    ${marked ? `<div class="xi-legend"><span><i class="xi-key xi-hit"></i>Predicted to start</span><span><i class="xi-key xi-miss"></i>Not predicted</span>
      <span><i class="xi-key-pick">Name <b>70</b></i>The model's pick instead, with his rank going into the match</span></div>` : ""}`;
}
// Marks each starter of an actual XI as predicted (hit) or not, against the model's pre-match XI
// ([id, name, role, rank] rows); a miss's instead is that row. Each starter it missed is paired with a predicted player who didn't
// start: same position first, then the same position group, then the same line, then anyone.
// Returns how many starters it got right.
const LINE_OF_ROLE = { GK: "GK", CB: "D", LB: "D", RB: "D", LWB: "D", RWB: "D", DM: "M", CM: "M", LM: "M", RM: "M", AM: "M", LW: "F", RW: "F", ST: "F" };
function markPredicted(xi, predicted) {
  const started = new Set(xi.map((c) => c.p.id));
  const picked = new Set(predicted.map(([pid]) => pid));
  const spare = predicted.filter(([pid]) => !started.has(pid));
  const missed = xi.filter((c) => !picked.has(c.p.id));
  for (const c of xi) c.predicted = picked.has(c.p.id);
  const tests = [(a, b) => a === b, (a, b) => GROUP_OF[a] === GROUP_OF[b], (a, b) => LINE_OF_ROLE[a] === LINE_OF_ROLE[b], () => true];
  for (const same of tests) for (const c of missed) {
    if (c.instead) continue;
    const i = spare.findIndex(([, , role]) => same(c.b.label, role));
    if (i !== -1) c.instead = spare.splice(i, 1)[0];
  }
  return xi.length - missed.length;
}

// ------------------------------------------------------------------ club page
const clubCache = new Map();

// The browser tab's title (also what a bookmark, the history list and a screen reader get): the
// tab or page name, then the site's
function setTitle(name) { document.title = name ? `${name} · The Corner FC` : "The Corner FC"; }
function showPage(name = "") {            // club, player and nationality pages share one panel
  setTitle(name);
  document.body.dataset.tab = "club";
  state.nation = null;
  document.querySelectorAll("nav.tabs button").forEach((b) => b.setAttribute("aria-selected", "false"));
  $("#app-title").textContent = "";
  document.querySelectorAll(".panel").forEach((p) => p.dataset.active = String(p.dataset.tab === "club"));
  window.scrollTo(0, 0);
}

async function openClubPage(id) {
  showPage(teamName(id));
  const body = $("#club-body");
  body.innerHTML = `<div class="empty-state">Loading ${escapeHtml(teamName(id))}…</div>`;
  const r = state.rankByTeam.get(id);
  // its league's file too, for the domestic table position
  const [club] = await Promise.all([loadClub(id), r?.in_league ? loadLeague(r.league) : null, loadPlayers()]);
  state.injuries ||=await getJsonOrNull("data/injuries.json");
  state.club = { id, data: club };
  renderClubPage();
  if (club && !club.positions && !state.playerSeasons) {   // position minutes for the overview pitch: redraw once loaded
    await seasonsFor(club);
    if (state.club?.id === id && (state.clubTab || "overview") === "overview") renderClubTab();
  }
}
// The club's injury list (injuries.json): its next match's, else its latest recent one
const clubInjuries = (id) => state.injuries?.teams?.[String(id)] || null;

const CLUB_TABS = [["overview", "Overview"], ["xi", "Predicted XI"], ["formations", "Formations"], ["matches", "Matches"], ["history", "History"]];
const clubOpp = (o) => state.club?.data?.teams?.[o] || teamName(o);
// his club's upcoming fixtures from the matches file
const clubUpcoming = (id) => state.data.matches.filter((m) => (m.home === id || m.away === id)
  && !FINISHED.has(m.status) && !["CANC", "PST", "ABD"].includes(m.status));
// a result's rank change: its rank after less the one before (the club file's start for the first)
function clubMove(rows, i, start) {
  const before = i > 0 ? rows[i - 1].rank : start;
  return before != null ? rows[i].rank - before : null;
}
const moveHtml = (v) => v == null ? "" : `<span class="${v > 0 ? "form-up" : v < 0 ? "form-down" : ""}">${v > 0 ? "+" : ""}${v.toFixed(1)}</span>`;

// ---- Key figures at the top of club and player pages. Everything is an exported value, a place
// counted among the exported values, or a difference between two of them: nothing new is modelled
const ordinal = (n) => { const s = ["th", "st", "nd", "rd"], v = n % 100; return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`; };
const signedInt = (v) => `${Math.round(v) > 0 ? "+" : Math.round(v) < 0 ? "−" : ""}${Math.abs(Math.round(v))}`;
const signedHtml = (v) => `<span class="${Math.round(v) > 0 ? "form-up" : Math.round(v) < 0 ? "form-down" : ""}">${signedInt(v)}</span>`;
const fmtLongDate = (iso) => parseDateInput(iso.slice(0, 10)).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const daysSince = (iso) => Math.floor((Date.now() - new Date(iso).getTime()) / 864e5);
// a club's place among every ranked club on one measure, and its badge colour (top 5% green ...)
const clubPlace = (key, v) => state.rankings.filter((x) => x[key] != null && x[key] > v).length + 1;
const placeTier = (place, of) => { const s = place / of; return s <= 0.05 ? 4 : s <= 0.2 ? 3 : s <= 0.5 ? 2 : 1; };
function kfTile(label, value, sub = "", tip = "", tier = null) {
  return `<div class="kf-tile${tier ? ` kf-t${tier}` : ""}"${tip ? ` title="${escapeHtml(tip)}"` : ""}>
    <div class="kf-label">${label}</div><div class="kf-value">${value}</div>${sub ? `<div class="kf-sub">${sub}</div>` : ""}</div>`;
}

// The club's row in its league's table (the first group it's in), if the league file has one
function domesticRow(id, lid) {
  const lg = leagueCache.get(lid);
  return lg?.tableRows?.find((t) => t.team === id) || null;
}

// Recent form above the tables: results in all competitions, newest first, as bare W/D/L chips (score
// and opponent on hover). As many as fit on one line: the strip hides the ones that wrap
function clubFormStrip() {
  const rows = (state.club?.data?.rows || []).slice(-40).reverse();
  if (!rows.length) return "";
  return `<div class="club-form lt-form">${rows.map((m) => {
    const c = m.gf > m.ga ? "W" : m.gf === m.ga ? "D" : "L";
    return `<i class="res-${c.toLowerCase()}" title="${escapeHtml(`${fmtShortDate(m.date)} · ${m.gf}–${m.ga} ${m.home ? "v" : "@"} ${clubOpp(m.opponent)} · ${compLabel(m.league)}`)}">${c}</i>`;
  }).join("")}</div>`;
}

// The club's slice of its league table, first on the page: it and the two clubs either side (five
// rows, shifted at the top and bottom), in the club's own group, zones coloured as on the Standings
function clubMiniTable(id) {
  const r = state.rankByTeam.get(id), lg = r?.in_league ? leagueCache.get(r.league) : null;
  const me = r?.in_league ? domesticRow(id, r.league) : null;
  if (!me) return "";
  const zones = leagueZones(lg.tableRows);
  const rows = lg.tableRows.filter((t) => t.group === me.group);
  const i = rows.indexOf(me), start = Math.max(0, Math.min(i - 2, rows.length - 5));
  const name = SHORT_NAMES[r.league] || state.data.competitions[r.league]?.name || compLabel(r.league);
  const title = me.group && me.group !== state.data.competitions[r.league]?.name ? `${name} · ${me.group}` : name;
  return `<div class="club-mini-table">
    <div class="table-scroll"><table class="league-table">
      <thead><tr><th class="cmt-head" colspan="3"><a class="cmt-link" href="${leagueHref(r.league)}/table">${escapeHtml(title)}<span class="cmt-full"> table</span> ›</a></th><th class="lt-wdl" title="Played">P</th>
        <th title="Goal difference">GD</th><th title="Points">Pts</th><th class="lt-formcol" title="Last five league games, newest first: green won, grey drawn, red lost">Form</th></tr></thead>
      <tbody>${rows.slice(start, start + 5).map((t) => `<tr${t === me ? ' class="lt-me"' : ""}>
        <td class="lt-pos" style="border-left-color:${zones.get(t.description) || "transparent"}">${t.rank}</td>
        <td class="lt-badge">${clubCrest(t.team, "club-logo", `data-club="${t.team}"`)}</td>
        <td class="lt-club lt-clubname"><span>${t === me ? `<b>${escapeHtml(lg.teams[t.team] || teamName(t.team))}</b>` : clubLink(t.team, lg.teams[t.team] || teamName(t.team))}</span></td>
        <td class="lt-wdl">${t.played ?? ""}</td><td>${t.gd > 0 ? "+" : ""}${t.gd ?? ""}</td><td><b>${t.points ?? ""}</b></td><td class="lt-formcol">${formChips(t.form)}</td></tr>`).join("")}</tbody>
    </table></div></div>`;
}

// Beside the table: the club's five best players by Ability, with this season's goals and assists
// (all his clubs, as on the Players view)
function clubBestPlayers(id) {
  const list = (state.players?.list || []).filter((p) => p.team === id && p.rank != null)
    .sort((a, b) => b.rank - a.rank).slice(0, 5);
  if (!list.length) return "";
  return `<div class="club-mini-table">
    <div class="table-scroll"><table class="league-table">
      <thead><tr><th class="cmt-head" colspan="2"><a class="cmt-link" href="#/players?club=${id}" title="All ${escapeHtml(teamName(id))} players in the Players ranking">Best players<span class="cmt-full"> · by Ability</span> ›</a></th><th title="${escapeHtml(ABILITY_TIP)}"><span class="cmt-full">Ability</span><span class="cmt-short">Abil.</span></th>
        <th title="Goals this season, all his clubs">G</th><th title="Assists this season, all his clubs">A</th></tr></thead>
      <tbody>${list.map((p) => `<tr>
        <td class="lt-badge">${personChip(p.name)}</td>
        <td class="lt-club"><a class="player-link" href="#/player/${p.id}"><span class="cmt-full">${escapeHtml(p.name)}</span><span class="cmt-short">${escapeHtml(shortName(p.name))}</span></a>${p.position ? ` <span class="bp-pos">${escapeHtml(p.position)}</span>` : ""}</td>
        <td>${rankChipSmall(p.rank)}</td><td>${p.season?.[2] ?? "–"}</td><td>${p.season?.[3] ?? "–"}</td></tr>`).join("")}</tbody>
    </table></div></div>`;
}

// ---- Style: the lean between attack and defence on a diverging meter (grey middle = balanced)
// the widest lean of any club, so the meter's ends are the world's extremes
const spMax = (a, b) => state[`spMax_${a}`] ||= Math.max(1, ...state.rankings.filter((x) => x[a] != null && x[b] != null)
  .map((x) => Math.abs(x[a] - x[b]) / 2));
function spMeter(label, lean, max, text, tip) {
  const x = 50 + 50 * Math.max(-1, Math.min(1, lean / max));
  return `<div class="sp-row" title="${escapeHtml(tip)}"><span class="sp-lbl">${label}</span>
    <span class="sp-track"><i class="sp-mid"></i><i class="sp-mark" style="left:${x.toFixed(1)}%"></i></span>
    <span class="sp-text">${text}</span></div>`;
}

function clubKeyFigures(id) {
  const r = state.rankByTeam.get(id);
  if (!r) return "";
  let cards = "";
  // Attack and defence average to Current Strength: the lean is half their difference (ranking.py
  // side_ratings)
  if (r.attack != null && r.defence != null) {
    const lean = (r.attack - r.defence) / 2, k = Math.round(lean);
    cards += `<div class="sp-card">
      ${spMeter("Style", lean, spMax("attack", "defence"), k === 0 ? "Balanced" : `${k > 0 ? "Attacking" : "Defensive"} ${signedInt(Math.abs(lean))}`,
        "Left (blue) defensive, right (orange) attacking, grey middle balanced. Attack and Defence average to Current Strength; the lean is half their difference. The ends are the most one-sided clubs in the world. Clubs in high-scoring games drift towards attack, low-scoring ones towards defence")}</div>`;
  }
  return cards ? `<div class="sp-grid">${cards}</div>` : "";
}

// A badge for the top right of a page's header: a rating coloured by its place among every ranked
// club, or a movement coloured green up, red down (rel-0 for level)
const heroRank = (v, label, tier, tip) => `<div class="pl-hero-rank rel-${tier}" title="${escapeHtml(tip)}">
  <span class="val">${typeof v === "number" ? Math.round(v) : v}</span><span class="lbl">${label}</span></div>`;

function renderClubPage() {
  const { id } = state.club;
  const r = state.rankByTeam.get(id);
  const comp = r ? state.data.competitions[r.league] : null;
  const tab = state.clubTab || "overview";
  const top = clubMiniTable(id) + clubBestPlayers(id);      // side by side, half the width each
  $("#club-body").innerHTML = `
    <div class="pl-hero">
      ${clubCrest(id, "club-logo-lg")}
      <div class="pl-hero-main">
        <h2>${escapeHtml(teamName(id))}</h2>
        ${comp ? `<div class="pl-hero-club">${flagLink(comp.country)}<span class="pl-league">${leagueLink(r.league)}</span></div>` : ""}
        ${state.club.data?.coach?.name || r ? `<div class="pl-hero-club pl-hero-nat">${state.club.data?.coach?.name ? `${personChip(state.club.data.coach.name, "player-photo coach-photo")}<span class="pl-meta">${escapeHtml(state.club.data.coach.name)}</span>` : ""}${
          state.club.data?.coach?.name && r ? `<span class="dim-sep">·</span>` : ""}${r ? `<a class="team-link" href="#" data-rank-team="${id}" data-rank-sort="current"
            title="Place among every ranked club by Current Strength, as the Club Rankings are ordered. Opens the Rankings at this club">#${clubPlace("current", r.current).toLocaleString()}</a>` : ""}</div>` : ""}
      </div>
      ${r ? `<div class="hero-ranks">${r.form != null ? heroRank(signedInt(r.form), "Last 6",
          Math.round(r.form) > 0 ? 4 : Math.round(r.form) < 0 ? 1 : 0, "Change in Current Strength over the club's last 6 matches, in all competitions") : ""
        }${heroRank(r.lt, "Baseline", placeTier(clubPlace("lt", r.lt), state.rankings.length),
          "Baseline Strength: the long-term level (LT ALGO), from every match since 2020")
        }${heroRank(r.current, "Current", placeTier(clubPlace("current", r.current), state.rankings.length),
          "Current Strength: the Elo rating after the latest match, from recent results")}</div>` : ""}
    </div>
    ${clubFormStrip()}
    ${top ? `<div class="club-top">${top}</div>` : ""}
    ${clubKeyFigures(id)}
    <div class="page-tabs" role="tablist">${CLUB_TABS.map(([k, label]) =>
      `<button type="button" role="tab" data-ctab="${k}" aria-selected="${k === tab}">${label}</button>`).join("")}</div>
    <div id="club-tab"></div>`;
  renderClubTab();
}

function renderClubTab() {
  const tab = state.clubTab || "overview";
  document.querySelectorAll("#club-body [data-ctab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.ctab === tab)));
  $("#club-tab").innerHTML = tab === "xi" ? clubXiTab() : tab === "formations" ? clubFormationsTab() : tab === "matches" ? clubMatchesTab()
    : tab === "history" ? clubHistoryTab() : clubOverviewTab();
}

// ---- Overview: injured and suspended players and recent form (newest first) beside the squad by
// position
function clubOverviewTab() {
  const { id, data } = state.club;
  const rows = data?.rows || [];
  const form = rows.slice(-10).map((m, k, arr) => ({ m, move: clubMove(rows, rows.length - arr.length + k, data.start) })).reverse();
  const formCard = form.length ? `<div class="next-card form-card">
      <div class="next-top"><span class="next-label">Recent results</span></div>
      <div class="form-row form-hdr"><span></span><span></span><span></span><span></span><span>xG</span><span title="How far each result moved Current Strength">Elo ±</span></div>
      ${form.map(({ m, move }) => `<div class="form-row" title="${escapeHtml(`${fmtShortDate(m.date)} ${m.home ? "v" : "@"} ${clubOpp(m.opponent)}${m.home === 2 ? " (neutral)" : ""} · ${compLabel(m.league)}`)}">
        <span class="rel-chip rel-${m.gf > m.ga ? 4 : m.gf === m.ga ? 3 : 1}">${m.gf}–${m.ga}</span>
        ${clubCrest(m.opponent, "club-logo", `data-club="${m.opponent}"`, clubOpp(m.opponent))}
        <span class="form-ha">${m.home === 2 ? "N" : m.home ? "H" : "A"}</span>
        ${leagueCrest(m.league, "next5-comp", `data-league="${m.league}" title="${escapeHtml(compLabel(m.league))}"`, compLabel(m.league))}
        <span class="form-xg${m.xg_est ? " est" : ""}" title="${m.xg_est ? "Estimated from shots (API-Football has no xG for this match): for – against" : "Expected goals: for – against"}">${
          m.xgf != null && m.xga != null ? `${m.xg_est ? "≈" : ""}${m.xgf.toFixed(1)}–${m.xga.toFixed(1)}` : "–"}</span>
        <span class="form-move">${moveHtml(move)}</span></div>`).join("")}
    </div>` : "";
  const upcoming = clubUpcoming(id).slice(0, 5);
  const nextCard = upcoming.length ? `<div class="next-card form-card">
      <div class="next-top"><span class="next-label">Fixtures</span></div>
      <div class="next5-row next5-hdr"><span></span><span></span><span></span><span></span><span title="Projected goals">Goals</span><span title="Clean sheet chance">CS</span><span title="Win chance">Win</span></div>
      ${upcoming.map((m) => {
        const home = m.home === id, opp = home ? m.away : m.home;
        const win = m.p_home != null ? Math.round(100 * (home ? m.p_home : m.p_away)) : null;
        // projected goals for and against; clean sheet = the chance the opponent scores none
        const gf = m.home_xg != null ? (home ? m.home_xg : m.away_xg) : null, ga = m.home_xg != null ? (home ? m.away_xg : m.home_xg) : null;
        const cs = ga != null ? Math.round(100 * Math.exp(-ga)) : null;
        const comp = SHORT_NAMES[m.league] || state.data.competitions[m.league]?.name || "";
        return `<div class="next5-row" title="${escapeHtml(`${fmtDay(m.kickoff)} ${fmtTime(m.kickoff)} · ${home ? "v" : "@"} ${teamName(opp)} · ${compLabel(m.league)}`)}">
          <span class="next5-date">${escapeHtml(fmtShortDate(m.kickoff))}</span>
          ${clubCrest(opp, "club-logo", `data-club="${opp}"`, teamName(opp))}
          <span class="form-ha">${home ? "H" : "A"}</span>
          ${leagueCrest(m.league, "next5-comp", `data-league="${m.league}" title="${escapeHtml(comp)}"`, comp)}
          <span class="next5-num">${gf != null ? gf.toFixed(1) : ""}</span>
          <span class="next5-num">${cs != null ? `${cs}%` : ""}</span>
          <span class="next5-num strong">${win != null ? `${win}%` : ""}</span></div>`;
      }).join("")}
    </div>` : "";
  // next match and availability beside the squad, then the fixtures after it and recent results
  const side = clubNextCard() + (injuredCard(id) || availabilityNote(id)), pitch = depthPitch(id);
  const lower = nextCard + formCard;
  return `
    ${side && pitch ? `<div class="ov-top"><div class="ov-side">${side}</div>${pitch}</div>` : side + pitch}
    ${lower ? `<div class="ov-row">${lower}</div>` : ""}
    <div class="page-note">Longer-term rating history is on the History tab.</div>`;
}
// With no one listed: say whether that's a clean list or no list at all
function availabilityNote(id) {
  const inj = clubInjuries(id);
  return `<div class="next-card inj-card"><div class="next-top"><span class="next-label">Injured &amp; Suspended</span></div>
    <div class="next-meta"><span>${inj ? "No one listed" : "No injury list for this club"}</span></div></div>`;
}

const BAN_REASONS = new Set(["Red Card", "Yellow Cards", "Suspended"]);
// A player page's injury entry ([fixture, type, ban]) in words: "Doubtful", "Suspended" or "Out".
// The injury itself is never shown
const availabilityWord = ([, type, ban]) => type === "Questionable" ? "Doubtful"
  : type === "Suspended" || BAN_REASONS.has(ban) ? "Suspended" : "Out";
// Injured (and suspended or doubtful) players, with how many matches in a row he has missed and
// his rank (the injury itself isn't shown, only "Doubtful" or the ban), from the club's injury
// list: the next match's, or its latest one if the next match's isn't out yet (bans already served are left out of that)
function injuredCard(id) {
  const inj = clubInjuries(id);
  if (!inj?.players.length) return "";
  const day = inj.kickoff.slice(0, 10);
  const past = state.club.data?.rows?.find((m) => m.date === day);
  const when = inj.upcoming ? "Next match" : `Latest list · ${past ? `${past.home ? "v" : "@"} ${escapeHtml(clubOpp(past.opponent))}, ` : ""}${escapeHtml(fmtShortDate(inj.kickoff))}`;
  return `<div class="next-card inj-card">
    <div class="next-top"><span class="next-label">Injured &amp; Suspended</span><span>${when}</span></div>
    ${inj.players.map((row) => [row, playerById(row[0])?.rank ?? row[5] ?? -1]).sort((a, b) => b[1] - a[1]).map(([row]) => row)
      .map(([pid, name, type, ban, missed, seasonRank]) => `<div class="inj-row">
      <div class="inj-top"><span class="inj-name" title="${escapeHtml(`${name}: missed his club's last ${missed} match${missed === 1 ? "" : "es"}`)}"><span class="inj-surname">${playerById(pid) ? playerLink(pid, shortName(name)) : escapeHtml(shortName(name))}</span>${missed ? `<span class="inj-missed">&nbsp;– ${missed}</span>` : ""}</span>
        ${(playerById(pid)?.rank ?? seasonRank) != null ? rankChipSmall(playerById(pid)?.rank ?? seasonRank) : `<span class="rel-chip rating-none" title="No rating: no minutes in the leagues with player data">–</span>`}</div>
      ${type === "Questionable" ? `<span class="inj-reason doubt">Doubtful</span>`
        : type === "Suspended" || BAN_REASONS.has(ban) ? `<span class="inj-reason susp">${escapeHtml(BAN_REASONS.has(ban) && ban !== "Suspended" ? `Suspended · ${ban}` : "Suspended")}</span>` : ""}</div>`).join("")}
  </div>`;
}

// The next match: when, who, the model's view and the predicted XI's rating
function clubNextCard() {
  const { id } = state.club;
  const m = clubUpcoming(id)[0];
  if (!m) return "";
  const home = m.home === id, opp = home ? m.away : m.home;
  const win = m.p_home != null ? Math.round(100 * (home ? m.p_home : m.p_away)) : null;
  const proj = m.home_xg != null ? `${(home ? m.home_xg : m.away_xg).toFixed(1)}–${(home ? m.away_xg : m.home_xg).toFixed(1)}` : "";
  const xiRating = home ? m.home_xi : m.away_xi;
  const missing = home ? m.home_missing : m.away_missing;
  return `<div class="next-card">
    <div class="next-top"><span class="next-label">${LIVE.has(m.status) ? "Live now" : "Next match"}</span>
      <span>${escapeHtml(fmtDay(m.kickoff))} · ${escapeHtml(fmtTime(m.kickoff))}</span></div>
    <div class="next-opp">${clubCrest(opp, "club-logo", `data-club="${opp}"`)}
      <span class="next-opp-name">${home ? "v" : "@"} ${clubLink(opp)}</span></div>
    <div class="next-meta"><span>${escapeHtml(compLabel(m.league))}</span>${win != null ? `<span>${win}% win</span>` : ""}${proj ? `<span>projected ${proj}</span>` : ""}
      ${xiRating != null ? `<span>XI rating ${Math.round(xiRating)}</span>` : ""}</div>
    ${missing ? `<div class="next-status warn">${missing} missing</div>` : ""}
  </div>`;
}

// ---- Predicted XI: the next match, the XI on the pitch and as a list
// A club's expected squad for a match, from clubDepth's expected minutes: strength = the minutes-
// weighted average position rank of everyone expected to play (bench minutes too); attack and
// defence weight each position by how much it attacks or defends
const SQUAD_WEIGHTS = {             // [attack, defence]
  GK: [0, 1], CB: [0.1, 1], LB: [0.3, 0.8], RB: [0.3, 0.8], LWB: [0.4, 0.6], RWB: [0.4, 0.6],
  CM: [0.5, 0.6], LM: [0.8, 0.3], RM: [0.8, 0.3], AM: [1, 0.2], LW: [1, 0.15], RW: [1, 0.15], ST: [1, 0.1],
};
function squadStrength(teamId, data, match) {
  const d = clubDepth(teamId, data, match);
  if (!d) return null;
  const sum = { all: [0, 0], att: [0, 0], def: [0, 0] };
  for (const b of d.shown) {
    const [wa, wd] = SQUAD_WEIGHTS[b.label] || [0.5, 0.5];
    for (const { p, rank } of b.ps) {
      const m = d.xMins.get(`${b.label}:${p.id}`) || 0;
      sum.all[0] += rank * m; sum.all[1] += m;
      sum.att[0] += rank * m * wa; sum.att[1] += m * wa;
      sum.def[0] += rank * m * wd; sum.def[1] += m * wd;
    }
  }
  const avg = ([a, b]) => b ? a / b : null;
  return sum.all[1] ? { strength: avg(sum.all), attack: avg(sum.att), defence: avg(sum.def) } : null;
}
// A club's file (cached), for club pages and match cards
async function loadClub(id) {
  if (clubCache.has(id)) return clubCache.get(id);
  const club = await getJsonOrNull(`data/clubs/${id}.json`);
  if (club) club.rows = rowsToObjects(club.fields, club.matches);
  clubCache.set(id, club);
  return club;
}
// Start chance colour: 80%+ green, 60-80 yellow, 40-60 orange, under 40 red
const startTier = (c) => (c = Math.round(c)) >= 80 ? 4 : c >= 60 ? 3 : c >= 40 ? 2 : 1;   // as shown, rounded
// The predicted XI from the overview's start chances: each position's usual number of starters,
// one position per player, filled from the surest picks down
function predictedXi(teamId, data = state.club?.data, match = null) {
  const d = clubDepth(teamId, data, match);
  if (!d) return null;
  const filled = new Map(), placed = new Set(), xi = [];
  d.shown.flatMap((b) => b.n ? b.ps.map(({ p, rank }) => ({ b, p, rank, chance: d.startChance.get(`${b.label}:${p.id}`) || 0 })) : [])
    .filter((c) => c.chance > 0).sort((x, y) => y.chance - x.chance || y.rank - x.rank).forEach((c) => {
      if (placed.has(c.p.id) || (filled.get(c.b.label) || 0) >= c.b.n) return;
      placed.add(c.p.id);
      filled.set(c.b.label, (filled.get(c.b.label) || 0) + 1);
      xi.push({ ...c, mins: d.xMins.get(`${c.b.label}:${c.p.id}`) || 0 });
    });
  return xi.length ? xi : null;
}
function clubXiTab() {
  const { id } = state.club;
  const xi = predictedXi(id);
  if (!xi) return `<div class="empty-state">No predicted XI for this club (it needs player data from its recent matches).</div>`;
  const pitch = xiPitch(xi);
  // the expected squad's attack, defence and strength (as on the match cards)
  const sq = squadStrength(id, state.club.data);
  const tile = (label, v, tip) => `<div class="sq-tile" title="${tip}"><span class="sq-lbl">${label}</span><span class="rel-chip rel-${rankTier(v)}">${Math.round(v)}</span></div>`;
  const squadCard = sq ? `<div class="next-card squad-card">
      <div class="next-top"><span class="next-label">Squad</span></div>
      <div class="sq-tiles">
        ${tile("Attack", sq.attack, "Expected players' ratings, weighted by expected minutes and how much each position attacks")}
        ${tile("Defence", sq.defence, "Expected players' ratings, weighted by expected minutes and how much each position defends")}
        ${tile("Strength", sq.strength, "Every expected player's rating, weighted by expected minutes (bench minutes included)")}
      </div></div>` : "";
  const side = clubNextCard() + squadCard;
  return `
    ${side ? `<div class="ov-top"><div class="ov-side">${side}</div>${pitch}</div>` : pitch}`;
}
// The predicted XI on a pitch as the overview's: keeper at the top, attacking down, left-sided
// positions on the right. Players in the same position are spread along its line.
function xiPitch(xi, data = state.club?.data, opts = {}) {
  const spot = Object.fromEntries(PITCH_SPOTS.map(([r, x, y]) => [r, [x, y]]));
  Object.assign(spot, { LM: [18, 34], RM: [82, 34] });
  const lines = new Map();                       // y -> players on that line
  for (const c of xi) {
    const [x0, y0] = spot[c.b.label] || spot.CM;
    const x = 100 - x0, y = Math.round(100 - y0) + (y0 > 85 ? 1 : 0);
    if (!lines.has(y)) lines.set(y, []);
    lines.get(y).push({ c, x });
  }
  const spots = [...lines].flatMap(([y, ps]) => {
    ps.sort((a, b) => a.x - b.x);
    const xs = ps.map((q) => q.x);
    // too close together: spread evenly around their middle, 24% apart (less if that won't fit)
    const clash = xs.some((v, i) => i && v - xs[i - 1] < 22);
    const gap = Math.min(24, 72 / Math.max(1, ps.length - 1)), width = gap * (ps.length - 1);
    const from = Math.min(Math.max(xs.reduce((a, v) => a + v, 0) / xs.length - width / 2, 14), 86 - width);
    return ps.map((q, i) => {
      const x = clash ? from + i * gap : q.x;
      const { b, p, rank, chance, mins, predicted, instead } = q.c;
      const hasChance = chance != null, hasMins = mins != null, marked = predicted != null;
      // an actual XI marked against the prediction: green if predicted to start, red if not
      const cls = marked ? `xi-mark ${predicted ? "xi-hit" : "xi-miss"}` : `sq-${hasChance ? startTier(chance) : rankTier(rank)}`;
      const rankText = rank == null ? "–" : Math.round(rank);
      const meta = hasChance || hasMins ? `<span class="pp-meta">${hasChance ? `<span class="sc-${startTier(chance)}">${Math.round(chance)}%</span>` : ""}${
        hasChance && hasMins ? " · " : ""}${hasMins ? `${mins}′` : ""}</span>` : `<span class="pp-meta">${escapeHtml(b.label || "")}</span>`;
      const [, predName, , predRank] = instead || [];
      const verdict = !marked ? "" : predicted ? " · predicted to start" : ` · not predicted${instead ? `; the model picked ${predName} (rank ${predRank != null ? Number(predRank).toFixed(1) : "–"})` : ""}`;
      // the square in the start-chance colour (or ringed green / red when marked), the rating in its own
      return `<a class="pp-spot xi-spot ${cls}" href="#/player/${p.id}" style="left:${x}%;top:${y}%"
          title="${escapeHtml(`${p.name} · ${b.label} · rank ${rank != null ? Number(rank).toFixed(1) : "–"}${hasChance ? ` · ${Math.round(chance)}% to start` : ""}${hasMins ? ` · ${mins}′ expected` : ""}${verdict}`)}">
        <span class="pp-rank rk-${rankTier(rank)}">${rankText}</span><span class="pp-name">${escapeHtml(shortName(p.name))}</span>
        ${meta}${instead ? `<span class="pp-instead"><span class="pp-instead-name">${escapeHtml(shortName(predName))}</span><span class="pp-instead-rank rk-${rankTier(predRank)}">${predRank == null ? "–" : Math.round(predRank)}</span></span>` : ""}</a>`;
    });
  }).join("");
  const ranks = xi.map((c) => c.rank).filter((r) => r != null);
  const avg = ranks.reduce((t, r) => t + r, 0) / ranks.length;
  return `<div class="club-section pp-section"><div class="pitch pp-pitch${kitClass(data)}"${kitStyle(data)}>${PITCH_LINES}${spots}</div>
    ${opts.note === "" ? "" : `<div class="page-note" style="text-align:center">${opts.note || (Number.isFinite(avg) ? `Average rank ${Math.round(avg)}` : "")}</div>`}</div>`;
}

// Overview pitch: in each position, the squad's players who can play there (their main position,
// or 2+ full matches' worth of starting minutes there over the last 12 months; until the
// position minutes have loaded, the 25% rule of the position filter), best first by their rank in
// that position, all of them. Only the positions in the formations used this season. Keeper at the top, strikers at the bottom (attacking down the
// page, so the left-sided positions are on the right). Laid out as a grid of lines so long lists push the pitch taller
// instead of overlapping.
const DEPTH_MINUTES = 180;
// The roles in a formation ("4-2-3-1" -> GK LB CB RB DM LW AM RW ST), as positions.py role()
function formationRoles(f) {
  const lines = String(f).split("-").map(Number);
  if (!lines.length || lines.some((n) => !(n > 0))) return [];
  const wide = (n, col, l, m, r) => col === 1 ? l : col === n ? r : m;
  const last = lines.length - 1, backThree = lines[0] === 3, middles = last - 1;
  const out = new Set(["GK"]);
  lines.forEach((n, idx) => {
    for (let col = 1; col <= n; col++) {
      let r;
      if (idx === 0) r = n === 4 ? wide(n, col, "LB", "CB", "RB") : n === 5 ? wide(n, col, "LWB", "CB", "RWB") : "CB";
      else if (idx === last) r = n >= 3 ? wide(n, col, "LW", "ST", "RW") : "ST";
      else if (middles === 1 || idx === 1) {
        if (middles !== 1 && n <= 2) r = "DM";
        else if (n === 4) r = backThree ? wide(n, col, "LWB", "CM", "RWB") : wide(n, col, "LM", "CM", "RM");
        else if (n === 5) r = wide(n, col, "LWB", "CM", "RWB");
        else r = "CM";
      } else if (n <= 2) r = idx === last - 1 ? "AM" : "CM";
      else if (n === 4) r = wide(n, col, "LM", "CM", "RM");
      else r = wide(n, col, "LW", "AM", "RW");
      out.add(r);
    }
  });
  return [...out];
}
// This season's matches: the formations the overview pitch takes its positions from
function clubFormationRows(data = state.club?.data) {
  const rows = data?.rows || [];
  if (!rows.length) return [];
  const { seasonOf } = clubSeasons(rows);
  const season = seasonOf(rows[rows.length - 1]);
  return rows.filter((m) => seasonOf(m) === season);
}
function canPlay(p) {
  const own = clubCache.get(p.team)?.positions;      // his club's file: {player: [[role, minutes], ...]}
  const rows = own ? own[String(p.id)] : state.playerSeasons?.positions?.[String(p.id)]?.["12m"];
  if (!rows) return playsAt(p);
  return new Set([p.position, ...rows.filter(([r, m]) => r !== "SUB" && m >= DEPTH_MINUTES).map(([r]) => r)]);
}
// data: the club's file (default: the open club page's); match: the fixture to work it out for
// (default: the club's next), which sets the kind of competition it leans on
function clubDepth(teamId, data = state.club?.data, match = null) {
  const out = new Set((clubInjuries(teamId)?.players || []).map(([pid]) => pid));   // injured: in their own box
  const atClub = new Set((state.players?.list || []).filter((p) => p.team === teamId).map((p) => p.id));
  const squad = (state.players?.list || []).filter((p) => p.team === teamId && !out.has(p.id));
  if (!squad.length) return null;
  const rankAt = (p, r) => p.position_ranks?.[GROUP_OF[r]] ?? (GROUP_OF[p.position] === GROUP_OF[r] ? p.rank : null);
  // only the positions in the formations the club has used (all of them if none are known)
  // a formation used only once this season (a one-off 4-4-2) is left out of the predictions,
  // unless no formation has been used more than once
  const formationCount = new Map();
  for (const m of clubFormationRows(data)) if (m.formation) formationCount.set(m.formation, (formationCount.get(m.formation) || 0) + 1);
  const oneOff = new Set([...formationCount.values()].some((n) => n > 1)
    ? [...formationCount].filter(([, n]) => n === 1).map(([f]) => f) : []);
  const used = new Set([...formationCount.keys()].filter((f) => !oneOff.has(f)).flatMap(formationRoles));
  // one box per position; DM and CM share one central-midfield box over both lines (the line-up
  // grid can't tell a holder from a box-to-box midfielder in a pair), his best rank of the two
  const boxes = PITCH_SPOTS.filter(([r]) => r !== "DM" && r !== "CM").map(([r, x, y]) =>
    ({ label: r, roles: [r], row: y < 20 ? 6 : y < 35 ? 5 : y < 50 ? 4 : y < 65 ? 3 : y < 80 ? 2 : 1, col: x < 35 ? 3 : x < 65 ? 2 : 1 }));
  boxes.push({ label: "CM", roles: ["DM", "CM"], row: "3 / span 2", col: 2 });
  // his share of the club's matches this season (with a line-up) that he started in this box
  const st = data?.starts;
  const startPct = (p, roles) => {
    const n = roles.reduce((a, r) => a + (st?.players?.[String(p.id)]?.[r] || 0), 0);
    return st?.games && n ? Math.round(100 * n / st.games) : null;
  };
  // how many usually start in this box: its starts this season per match (everyone who started
  // there, including players since gone or now injured)
  const usualExact = (roles) => st?.games ? Object.values(st.players || {})
    .reduce((a, byRole) => a + roles.reduce((b, r) => b + (byRole[r] || 0), 0), 0) / st.games : 0;
  // The share each available player is expected to start in this box: his own starts there this
  // season, plus a cut of the starts of players now injured or gone. That missing share goes to
  // the players who have started there since the last of them did (Konsa for Mosquera, Timber
  // for White), then to the others by rank (each 3 points lower halves it), each start there
  // this season adding one more share, so a better player is likelier (Randall over Duffy for
  // Koroma); nobody over 100%. Only players who really play there take it (his main position,
  // 180+ starting minutes there in a year, or a start there this season by a player who isn't a
  // regular starter elsewhere): a one-off cup start somewhere new (Zubimendi at right-back in a
  // rotated League Cup side) keeps its own few % but doesn't inherit anyone's.
  // It's worked out for the next match's kind of competition: league, European or domestic cup.
  // Over this season's matches of that kind, blended with all its matches in proportion
  // k : 1 (k = matches of that kind), so a rotated League Cup side lifts the reserves for the next
  // cup tie and a league match leans on the league regulars.
  const xiFormation = st?.xi_formation || [];
  const keep = (_, k) => !oneOff.has(xiFormation[k]);
  const xi = (st?.xi || []).filter(keep), xiLeague = (st?.xi_league || []).filter(keep);
  const seasonXi = xi;                                  // projectedIn's own xi is one kind of competition
  const compGroup = (lg) => {
    const c = state.data.competitions[lg];
    return !c ? "cup" : c.type === "League" ? "league" : c.country === "World" ? "europe" : "cup";
  };
  const nextMatch = match || clubUpcoming(teamId)[0];
  const nextGroup = nextMatch ? compGroup(nextMatch.league) : null;
  const groupXi = nextGroup ? xi.filter((_, k) => compGroup(xiLeague[k]) === nextGroup) : [];
  const wGroup = groupXi.length / (groupXi.length + 1);
  // starters per match in a box, over the same competition-weighted matches as the shares
  const perMatch = (matches, roles) => matches.length ? matches.reduce((t, m) => {
    for (let i = 0; i < m.length; i += 2) if (roles.includes(m[i + 1])) t++;
    return t;
  }, 0) / matches.length : null;
  const exactFor = (roles) => {
    const all = perMatch(xi, roles) ?? usualExact(roles);
    return groupXi.length ? wGroup * perMatch(groupXi, roles) + (1 - wGroup) * all : all;
  };
  const shareIn = (matches, p, roles) => {
    if (!matches.length) return 0;
    let c = 0;
    for (const m of matches) for (let i = 0; i < m.length; i += 2) if (m[i] === p.id && roles.includes(m[i + 1])) c++;
    return 100 * c / matches.length;
  };
  const projectedIn = (roles, n, ps, xi) => {
    const actual = new Map(ps.map(({ p }) => [p.id, shareIn(xi, p, roles)]));
    const share = new Map(actual);
    let left = n * 100 - [...actual.values()].reduce((a, v) => a + v, 0);
    if (left <= 0.5) return { share, changed: false };
    let last = -1;
    xi.forEach((m, k) => {
      for (let i = 0; i < m.length; i += 2) if (roles.includes(m[i + 1]) && (out.has(m[i]) || !atClub.has(m[i]))) last = k;
    });
    if (last < 0) return { share, changed: false };   // short only because the formation varies
    const startsIn = (id, inBox, matches = xi) => matches.reduce((t, m) => {
      for (let i = 0; i < m.length; i += 2) if (m[i] === id && roles.includes(m[i + 1]) === inBox) t++;
      return t;
    }, 0);
    const season = seasonXi;                             // a start there in any competition counts
    const regular = ps.filter(({ p }) => roles.some((x) => canPlay(p).has(x))
      || (startsIn(p.id, true, season) && startsIn(p.id, false, season) <= season.length / 2));
    const pool = regular.length ? regular : ps;
    const room = (id) => 100 - share.get(id);
    const hand = (weights) => {                          // share out what's left by these weights
      const wsum = weights.reduce((a, [, w]) => a + w, 0);
      if (left <= 0.5 || !wsum) return;
      const give = left;
      for (const [id, w] of weights) { const g = Math.min(room(id), give * w / wsum); share.set(id, share.get(id) + g); left -= g; }
    };
    const since = new Map();
    for (const m of xi.slice(last + 1)) for (let i = 0; i < m.length; i += 2)
      if (roles.includes(m[i + 1])) since.set(m[i], (since.get(m[i]) || 0) + 1);
    hand(pool.map(({ p }) => [p.id, since.get(p.id) || 0]));
    const top = Math.max(...pool.map((d) => d.rank));
    hand(pool.map(({ p, rank }) => [p.id, 2 ** ((rank - top) / 3) * (1 + startsIn(p.id, true))]));
    for (const { p } of pool) { if (left <= 0.5) break; const g = Math.min(room(p.id), left); share.set(p.id, share.get(p.id) + g); left -= g; }
    return { share, changed: true };
  };
  const projected = (roles, n, ps) => {
    const all = projectedIn(roles, n, ps, xi);
    if (!groupXi.length) return all;
    const grp = projectedIn(roles, n, ps, groupXi);
    const share = new Map(ps.map(({ p }) => [p.id, wGroup * (grp.share.get(p.id) || 0) + (1 - wGroup) * (all.share.get(p.id) || 0)]));
    return { share, changed: all.changed || grp.changed };
  };
  const nextLabel = nextMatch ? SHORT_NAMES[nextMatch.league] || state.data.competitions[nextMatch.league]?.name || "" : "";
  // Each box: who's in it, how many usually start there and the expected shares from history
  const visible = boxes.filter((b) => !used.size || b.roles.some((r) => used.has(r)));
  // who can play in a box, and anyone who has started there this season
  const fits = (p, b) => b.roles.some((x) => canPlay(p).has(x)) || startPct(p, b.roles);
  // a squad player with no box (his position isn't in this season's formations: a wing-back when
  // the club plays a back four) goes in the nearest one it does use, so everyone is on the pitch
  const NEAR = { LWB: ["LB", "LM", "CB"], RWB: ["RB", "RM", "CB"], LB: ["LWB", "CB"], RB: ["RWB", "CB"],
                 LW: ["LM", "AM", "ST"], RW: ["RM", "AM", "ST"], LM: ["LW", "CM", "AM"], RM: ["RW", "CM", "AM"],
                 AM: ["CM", "LW", "RW", "ST"], DM: ["CM", "CB"], CM: ["CM", "AM"], ST: ["AM", "LW", "RW"], CB: ["LB", "RB", "CM"] };
  const labels = new Set(visible.map((b) => b.label));
  const fallback = new Map(squad.filter((p) => !visible.some((b) => fits(p, b)))
    .map((p) => [p.id, (NEAR[p.position] || []).find((l) => labels.has(l)) || (labels.has("CM") ? "CM" : null)]));
  // Starters per box: its starters per match rounded to whole players that make an XI, the
  // largest fractions taking the places left after rounding down (LW 0.85 is 1, LM 0.01 is 0),
  // so each box fills to 100% per starter and the pitch to 11 even where a match's line-up is
  // missing a player's position
  const exactOf = new Map(visible.map((b) => [b.label, exactFor(b.roles)]));
  const starters = new Map([...exactOf].map(([l, x]) => [l, Math.floor(x)]));
  let places = [...exactOf.values()].some((x) => x > 0) ? 11 - [...starters.values()].reduce((t, x) => t + x, 0) : 0;
  for (const [l, x] of [...exactOf].sort((a, b) => (b[1] % 1) - (a[1] % 1))) {
    if (places <= 0 || x % 1 === 0) break;
    starters.set(l, starters.get(l) + 1);
    places--;
  }
  const shown = visible.map((b) => {
    const n = starters.get(b.label);
    const ps = squad.filter((p) => fits(p, b) || fallback.get(p.id) === b.label)
      .map((p) => ({ p, rank: Math.max(...b.roles.map((x) => rankAt(p, x) ?? -1)) }))
      .map((d) => ({ ...d, rank: d.rank >= 0 ? d.rank : d.p.rank }))
      .sort((x, y) => y.rank - x.rank);
    return { ...b, n, exact: n, ps, proj: ps.length ? projected(b.roles, n, ps) : null };
  });
  // The best XI by rating: the usual number of starters in each box, filled from the highest
  // player-and-position ranks down, one position per player (Odegaard's 92 in midfield puts him
  // there and Eze at AM; a tie goes to where he plays). A pick only counts if he's rated above
  // one of the box's usual starters (by expected share) or is one himself, so the pull only ever
  // moves minutes to a better player. The expected share is ABILITY_PULL of that and the rest
  // history, so a better player the manager hasn't picked yet still gets some minutes (Hincapie
  // over Calafiori at LB).
  const ABILITY_PULL = 0.2;
  const picks = new Map(), placed = new Set(), filled = new Map();   // box -> [player ids]
  const histOf = (b, id) => b.proj?.share.get(id) || 0;
  shown.flatMap((b) => b.n ? b.ps.map((d) => ({ b, ...d, h: histOf(b, d.p.id) })) : [])
    .sort((x, y) => y.rank - x.rank || y.h - x.h).forEach(({ b, p }) => {
      if (placed.has(p.id) || (filled.get(b.label) || 0) >= b.n) return;
      placed.add(p.id);
      filled.set(b.label, (filled.get(b.label) || 0) + 1);
      if (!picks.has(b.label)) picks.set(b.label, []);
      picks.get(b.label).push(p.id);
    });
  // per box: 100 for each counting pick, the rest of its starts shared by history among the others
  const ability = new Map();
  for (const b of shown) {
    if (!b.n || !b.ps.length) continue;
    const starters = [...b.ps].sort((x, y) => histOf(b, y.p.id) - histOf(b, x.p.id)).slice(0, b.n);
    const worst = Math.min(...starters.map((d) => d.rank));
    const rankOf = new Map(b.ps.map((d) => [d.p.id, d.rank]));
    const count = (picks.get(b.label) || []).filter((id) => starters.some((d) => d.p.id === id) || rankOf.get(id) > worst);
    const rest = b.ps.filter((d) => !count.includes(d.p.id));
    const restHist = rest.reduce((a, d) => a + histOf(b, d.p.id), 0);
    const left = Math.max(0, b.n - count.length) * 100;
    const m = new Map(b.ps.map((d) => [d.p.id, count.includes(d.p.id) ? 100
      : restHist ? left * histOf(b, d.p.id) / restHist : 0]));
    ability.set(b.label, m);
  }
  // Start chance per player and box: history with the pull towards the best XI
  const startChance = new Map();                       // "box:player" -> %
  for (const { label: r, n, ps, proj } of shown) {
    const ab = ability.get(r);
    for (const { p } of ps) {
      const hist = proj?.share.get(p.id) || 0;
      startChance.set(`${r}:${p.id}`, ab ? (1 - ABILITY_PULL) * hist + ABILITY_PULL * Math.min(100, ab.get(p.id) || 0) : hist);
    }
  }
  // A player starts in one position at most: his chances across boxes can't pass 100%. Over it,
  // he keeps his likeliest positions (Tavernier at LW) and gives up the rest; each box then tops
  // its starts back up to its exact starters per match from its other players with room, by
  // their chance there (or their rank if nobody has one)
  const totalChance = (id) => shown.reduce((t, b) => t + (startChance.get(`${b.label}:${id}`) || 0), 0);
  for (const id of new Set(shown.flatMap((b) => b.ps.map(({ p }) => p.id)))) {
    let cap = 100;
    for (const b of [...shown].sort((x, y) => (startChance.get(`${y.label}:${id}`) || 0) - (startChance.get(`${x.label}:${id}`) || 0))) {
      const k = `${b.label}:${id}`;
      if (!startChance.has(k)) continue;
      const v = Math.min(startChance.get(k), cap);
      startChance.set(k, v);
      cap -= v;
    }
  }
  for (const b of shown) {
    let left = b.exact * 100 - b.ps.reduce((t, { p }) => t + startChance.get(`${b.label}:${p.id}`), 0);
    if (left < -0.5) {                                  // over its starters: scale the box down to them
      const k = b.exact * 100 / (b.exact * 100 - left);
      for (const { p } of b.ps) startChance.set(`${b.label}:${p.id}`, startChance.get(`${b.label}:${p.id}`) * k);
      left = 0;
    }
    for (const pass of ["chance", "rank"]) {
      if (left <= 0.5) break;
      const w = b.ps.map(({ p, rank }) => [p.id, pass === "chance" ? startChance.get(`${b.label}:${p.id}`) : rank]).filter(([, v]) => v > 0);
      const wsum = w.reduce((t, [, v]) => t + v, 0);
      const give = left;
      for (const [id, v] of w) {
        const k = `${b.label}:${id}`;
        const g = Math.min(give * v / wsum, 100 - totalChance(id), 100 - startChance.get(k));
        if (g > 0) { startChance.set(k, startChance.get(k) + g); left -= g; }
      }
    }
  }
  // Expected minutes in each box: as a starter, his start chance x how long he usually lasts when
  // he starts (last 12 months, blended towards a typical 90 for keepers and 80 for the rest over
  // his first few starts); off the bench, the minutes the box's starters are expected to leave
  // (it needs its exact starters per match x 90) shared among the squad players whose main
  // position is there, by their minutes per match off the bench; nobody over 90 in all
  const mins = st?.mins || {}, minsMatches = st?.mins_matches || 0;
  const lasts = (p) => {
    const [n = 0, m = 0] = mins[String(p.id)] || [], typical = GROUP_OF[p.position] === "GK" ? 90 : 80;
    return (m + 3 * typical) / (n + 3);
  };
  const benchRate = (p) => minsMatches ? ((mins[String(p.id)] || [])[3] || 0) / minsMatches : 0;
  const mainBox = (p) => (shown.find((b) => b.roles.includes(p.position)) || {}).label;
  const xMins = new Map(), boxMins = new Map();       // "box:player" -> minutes; box -> total
  for (const { label: r, exact, ps } of shown) {
    let starting = 0;
    for (const { p } of ps) {
      const m = startChance.get(`${r}:${p.id}`) / 100 * lasts(p);
      xMins.set(`${r}:${p.id}`, m);
      starting += m;
    }
    const demand = Math.max(0, exact * 90 - starting);
    // off the bench: by minutes per match as a sub, times his chance of not starting anywhere (a
    // certain starter can't also come on); nobody who comes on there: the box's players by that
    const notStarting = ({ p }) => Math.max(0, 100 - totalChance(p.id)) / 100;
    const subW = ({ p }) => benchRate(p) * notStarting({ p });
    let bench = ps.filter((d) => mainBox(d.p) === r && subW(d) > 0);
    if (!bench.length) bench = ps.filter((d) => subW(d) > 0);
    const weight = bench.length ? subW : notStarting;
    if (!bench.length) bench = ps;
    const wsum = bench.reduce((t, d) => t + weight(d), 0);
    if (wsum) for (const d of bench) xMins.set(`${r}:${d.p.id}`, xMins.get(`${r}:${d.p.id}`) + demand * weight(d) / wsum);
  }
  for (const id of new Set(shown.flatMap((b) => b.ps.map(({ p }) => p.id)))) {
    const keys = shown.map((b) => `${b.label}:${id}`).filter((k) => xMins.has(k));
    let over = keys.reduce((t, k) => t + xMins.get(k), 0) - 90;
    for (const k of [...keys].sort((x, y) => xMins.get(x) - xMins.get(y))) {
      if (over <= 0) break;
      const cut = Math.min(over, xMins.get(k));
      xMins.set(k, xMins.get(k) - cut);
      over -= cut;
    }
  }
  const PARTNER = { LM: "LW", LW: "LM", RM: "RW", RW: "RM", LWB: "LB", LB: "LWB", RWB: "RB", RB: "RWB",
                   AM: "CM", CM: "AM", ST: "AM" };
  const playerMins = (id) => shown.reduce((t, b) => t + (xMins.get(`${b.label}:${id}`) || 0), 0);
  const topUp = (label, need, into) => {                // give `need` minutes to box `into`'s players
    const b = shown.find((x) => x.label === into);
    if (!b) return need;
    for (const pass of [0, 1]) {
      const w = b.ps.map(({ p, rank }) => [p.id, rank, 90 - playerMins(p.id)]).filter(([, , room]) => room > 0.01);
      const wsum = w.reduce((t, [, r]) => t + r, 0);
      if (!wsum || need <= 0.01) break;
      const give = need;
      for (const [id, r, room] of w) {
        const g = Math.min(room, give * r / wsum);
        xMins.set(`${into}:${id}`, (xMins.get(`${into}:${id}`) || 0) + g);
        need -= g;
      }
    }
    return need;
  };
  for (const b of shown) {
    const short = b.exact * 90 - b.ps.reduce((t, { p }) => t + (xMins.get(`${b.label}:${p.id}`) || 0), 0);
    if (short > 0.01) { const rest = topUp(b.label, short, b.label); if (rest > 0.01 && PARTNER[b.label]) topUp(b.label, rest, PARTNER[b.label]); }
  }
  for (const { label: r, ps } of shown) {
    // whole minutes that add up to the box's total (largest remainders get the spare minutes)
    const raw = ps.map(({ p }) => [p.id, Math.min(90, xMins.get(`${r}:${p.id}`) || 0)]);
    const total = Math.round(raw.reduce((t, [, v]) => t + v, 0));
    const whole = new Map(raw.map(([id, v]) => [id, Math.floor(v)]));
    let spare = total - [...whole.values()].reduce((t, v) => t + v, 0);
    for (const [id] of [...raw].sort((x, y) => (y[1] % 1) - (x[1] % 1))) { if (spare <= 0) break; whole.set(id, whole.get(id) + 1); spare--; }
    for (const [id, v] of whole) xMins.set(`${r}:${id}`, v);
    boxMins.set(r, total);
  }
  return { shown, startChance, xMins, boxMins, picks, nextLabel, startPct, lasts, benchRate };
}
function depthPitch(teamId) {
  const d = clubDepth(teamId);
  if (!d) return "";
  const { shown, startChance, xMins, boxMins, picks, nextLabel, startPct, lasts, benchRate } = d;
  const spots = shown.map(({ label: r, roles, row, col, n, ps, proj }) => {
    const label = `${r}${n ? `<span class="dp-usual"> – ${n}</span>` : ""}`;
    const cell = `grid-row:${row};grid-column:${col}`;
    if (!ps.length) return `<div class="dp-spot empty" style="${cell}"><span class="dp-pos">${label}</span></div>`;
    return `<div class="dp-spot" style="${cell}">
      <span class="dp-pos" title="${n ? `${n} usually start${n === 1 ? "s" : ""} here this season` : ""}">${label}<span class="dp-total" title="Expected minutes in this position, all its players">${
        boxMins.get(r) || 0}′</span></span>
      ${ps.map(({ p, rank }) => {
        const share = startChance.get(`${r}:${p.id}`) || 0;
        const got = Math.round(share), had = startPct(p, roles) || 0;
        const pct = got || null;
        const xmin = xMins.get(`${r}:${p.id}`) || 0;
        const tip = `${p.name}: ${got}% chance of starting at ${r} in the next match${nextLabel ? ` (${nextLabel})` : ""}`
          + ` (started ${had}% of this season's matches there${proj.changed ? "; allowing for the injured or departed" : ""})`
          + ((picks.get(r) || []).includes(p.id) ? " · in the best XI by rating" : "")
          + ` · xMins ${xmin}: lasts ${Math.round(lasts(p))}′ when he starts${benchRate(p) ? `, ${Math.round(benchRate(p))}′ a match off the bench` : ""}`;
        return `<a class="dp-row" href="#/player/${p.id}" title="${escapeHtml(tip)}">
          <span class="dp-name">${escapeHtml(shortName(p.name))}</span><span class="dp-pct">${pct != null ? `${pct}%` : ""}</span>
          <span class="dp-rank t${rankTier(rank)}">${Math.round(rank)}</span><span class="dp-xmin${xmin ? "" : " zero"}">${xmin}′</span></a>`;
      }).join("")}
    </div>`;
  }).join("");
  return `<div class="club-section pp-section"><div class="pitch dp-pitch${kitClass()}"${kitStyle()}>${PITCH_LINES}${spots}</div></div>`;
}
// The club's home kit colours (club file) for its pitches: stripes in the shirt colour, lines in
// the number colour; clubs without them keep the plain dark pitch
const HEX = /^[0-9a-f]{6}$/i;
const kitColors = (data = state.club?.data) => HEX.test(data?.colors?.[0] ?? "") ? data.colors : null;
const kitClass = (data = state.club?.data) => kitColors(data) ? " kit" : "";
const kitStyle = (data = state.club?.data) => {
  const c = kitColors(data);
  return c ? ` style="--kit:#${c[0]};--kit2:#${HEX.test(c[1] ?? "") ? c[1] : "ffffff"}"` : "";
};
// Surname for tight spaces, keeping lower-case particles ("M. de Ligt" -> "de Ligt"), or the
// name a player is known by where that isn't his surname
const KNOWN_AS = { "Gabriel Magalhães": "Gabriel" };
function shortName(name) {
  if (KNOWN_AS[name]) return KNOWN_AS[name];
  const parts = name.split(" ");
  let i = parts.length - 1;
  while (i > 1 && /^(de|da|do|dos|das|di|del|della|van|von|der|den|ten|ter|la|le|el|al|bin|ben)$/i.test(parts[i - 1])) i--;
  if (i === 1 && /^[a-z]/.test(parts[0])) i = 0;
  return parts.slice(i).join(" ");
}

// The predicted XI on the pitch: each player at his position with his rank. Players on the
// same line are spread evenly across it (two centre-backs, two left wingers ...).

// ---- Matches: upcoming fixtures, then every result since 2020 (newest first)
function clubMatchesTab() {
  const { id, data } = state.club;
  const upcoming = clubUpcoming(id);
  const rows = data?.rows || [];
  const addClubExtra = (card, extra) => card.replace(/<\/div>\s*$/, `${extra}</div>`);
  const fixture = (m) => {
    const home = m.home === id;
    const win = m.p_home != null ? Math.round(100 * (home ? m.p_home : m.p_away)) : null;
    const extra = `<div class="club-card-extra"><span>${escapeHtml(compLabel(m.league))}</span>${win != null ? `<span><b>${win}%</b> win</span>` : ""}</div>`;
    // The day as well as the time: a club's fixtures run over many days
    const meta = `${fmtDay(m.kickoff)} · ${fmtTime(m.kickoff)}${m.round ? ` · ${roundName(m.round)}` : ""}`;
    return addClubExtra(matchCard({ ...m, meta }, { lineups: false }), extra);
  };
  const LIMIT = state.club.allResults ? Infinity : 40;
  const thisYear = String(new Date().getFullYear());
  const results = rows.map((m, i) => ({ m, move: clubMove(rows, i, data.start) })).reverse();
  const view = (state.club.matchView === "results" || (!upcoming.length && results.length)) ? "results" : "fixtures";
  state.club.matchView = view;
  const result = ({ m, move }) => {
    const home = m.home !== 0;
    const card = {
      status: "FT",
      meta: `${fmtShortDate(m.date)}${m.date.slice(0, 4) !== thisYear ? ` '${m.date.slice(2, 4)}` : ""} · ${compLabel(m.league)}`,
      home: home ? id : m.opponent,
      away: home ? m.opponent : id,
      home_name: home ? teamName(id) : clubOpp(m.opponent),
      away_name: home ? clubOpp(m.opponent) : teamName(id),
      hg: home ? m.gf : m.ga,
      ag: home ? m.ga : m.gf,
      home_xg: m.xgf == null ? null : home ? m.xgf : m.xga,
      away_xg: m.xgf == null ? null : home ? m.xga : m.xgf,
      home_rank: home ? m.rank : null,
      away_rank: home ? null : m.rank,
    };
    return `<div class="match-card ${resClass(m).replace("res-", "club-res-")}">
      ${matchHead(card)}
      ${m.xi_lines ? `<div class="market-line" title="Average player rank (0-100) by line">Starting XI ${linesText(m.xi_lines)}</div>` : ""}
      <div class="club-card-extra">
        <span${m.attack != null ? ` title="Attack ${Math.round(m.attack)} · Defence ${Math.round(m.defence)} after the match"` : ""}>Elo <b>${m.rank.toFixed(1)}</b></span>
        <span class="rank-move">${moveHtml(move)}</span>
      </div>
    </div>`;
  };
  if (!upcoming.length && !results.length) return `<div class="empty-state">No matches for this club yet.</div>`;
  const toggle = `<div class="stats-controls" style="margin-top:0">
    <div class="seg">${[["fixtures", `Fixtures${upcoming.length ? ` (${upcoming.length})` : ""}`], ["results", `Results${results.length ? ` (${results.length})` : ""}`]].map(([k, label]) =>
      `<button type="button" data-club-match-view="${k}" aria-pressed="${k === view}">${escapeHtml(label)}</button>`).join("")}</div>
  </div>`;
  return `
    ${toggle}
    ${view === "fixtures" ? (upcoming.length ? `<div class="card-list">${upcoming.map(fixture).join("")}</div>
      <div class="page-note">Projected score and win chance from the model.</div>` : `<div class="empty-state">No upcoming fixtures for this club.</div>`) : ""}
    ${view === "results" ? (results.length ? `<div class="card-list" id="club-results">${results.slice(0, LIMIT).map(result).join("")}</div>
      ${results.length > LIMIT ? `<button type="button" class="show-all" data-club-more>Show all ${results.length.toLocaleString()}</button>` : ""}
      <div class="page-note">Elo: the club's Elo rating after the match; the change is how far that match moved it.</div>` : `<div class="empty-state">No results for this club yet.</div>`) : ""}`;
}


// A club's seasons: July to June, or the calendar year for clubs that play through the summer
// (more matches in June/July than in December/January: MLS, Norway ...)
function clubSeasons(rows) {
  const month = (m) => Number(m.date.slice(5, 7));
  const summer = rows.filter((m) => month(m) === 6 || month(m) === 7).length;
  const winter = rows.filter((m) => month(m) === 12 || month(m) === 1).length;
  const calendar = summer > winter;
  const seasonOf = (m) => { const y = Number(m.date.slice(0, 4)); return calendar ? y : month(m) >= 7 ? y : y - 1; };
  return { calendar, seasonOf, label: (y) => calendar ? String(y) : seasonShort(y) };
}

// ---- Formations: the manager, then the formations used since he took over and this season
// (league line-ups only: cup matches outside the player-data leagues have no formation)
function clubFormationsTab() {
  const { data } = state.club;
  const rows = data?.rows || [];
  if (!rows.some((m) => m.formation)) return `<div class="empty-state">No line-ups for this club (formations come from the leagues with match-by-match player data).</div>`;
  const coach = data.coach;
  const { seasonOf, label } = clubSeasons(rows);
  const season = seasonOf(rows[rows.length - 1]);
  const sinceRows = coach?.since ? rows.filter((m) => m.date >= coach.since) : [];
  const seasonRows = rows.filter((m) => seasonOf(m) === season);
  const section = (title, list) => {
    const known = list.filter((m) => m.formation);
    if (!known.length) return `<div class="club-section"><div class="modal-section">${title}</div><div class="page-note">No line-ups yet.</div></div>`;
    const missing = list.length - known.length;
    return `<div class="club-section"><div class="modal-section">${title}</div>${formationCards(known)}
      ${missing ? `<div class="page-note">${missing} match${missing === 1 ? "" : "es"} with no known line-up not counted.</div>` : ""}</div>`;
  };
  // the same matches either way (he took over before this season's first match): one list
  const same = sinceRows.length === seasonRows.length && sinceRows[0] === seasonRows[0];
  return `
    ${coach ? `<div class="next-card coach-card">
      ${personChip(coach.name, "coach-photo")}
      <div><div class="next-label">Manager</div><div class="coach-name">${escapeHtml(coach.name || "")}</div>
        <div class="next-meta">${coach.since ? `<span>Since ${escapeHtml(fmtLongDate(coach.since))}</span>` : ""}${sinceRows.length ? `<span>${sinceRows.length} matches · ${wdl(sinceRows)}</span>` : ""}</div></div>
    </div>` : ""}
    ${section(`${same && coach ? `Since ${escapeHtml(coach.name)} took over · ` : ""}This season (${label(season)})`, seasonRows)}
    ${coach?.since && !same ? section(`Since ${escapeHtml(coach.name)} took over`, sinceRows) : ""}`;
}
// W-D-L of a list of matches ({gf, ga})
const wdl = (list) => {
  const w = list.filter((m) => m.gf > m.ga).length, d = list.filter((m) => m.gf === m.ga).length;
  return `${w}W ${d}D ${list.length - w - d}L`;
};
// This year's dates as "5 Sep", older ones with the year
const fmtDateShortYear = (iso) => iso.slice(0, 4) === String(new Date().getFullYear()) ? fmtShortDate(iso) : fmtLongDate(iso);
// One card per formation in a list of matches with one ({date, formation, gf, ga}, oldest first):
// most used first, with its share, record and goals, and when it was last used
function formationCards(known) {
  const by = new Map();
  for (const m of known) { if (!by.has(m.formation)) by.set(m.formation, []); by.get(m.formation).push(m); }
  return `<div class="fm-grid">${[...by].sort((a, b) => b[1].length - a[1].length || b[1][b[1].length - 1].date.localeCompare(a[1][a[1].length - 1].date))
    .map(([f, ms], i) => {
      const share = 100 * ms.length / known.length;
      const gf = ms.reduce((a, m) => a + m.gf, 0), ga = ms.reduce((a, m) => a + m.ga, 0);
      return `<div class="fm-card${i === 0 ? " top" : ""}">${formationSvg(f)}
        <div class="fm-main"><div class="fm-name">${escapeHtml(f)}</div>
          <div class="fm-count">${ms.length} match${ms.length === 1 ? "" : "es"} · ${share < 1 ? "<1" : Math.round(share)}%</div>
          <div class="fm-bar"><span style="width:${share}%"></span></div>
          <div class="fm-sub">${wdl(ms)} · ${gf}–${ga}</div>
          <div class="fm-sub">last ${escapeHtml(fmtDateShortYear(ms[ms.length - 1].date))}</div></div></div>`;
    }).join("")}</div>`;
}
// A formation ("4-2-3-1") drawn as dots on a small pitch: keeper at the top, attacking down
function formationSvg(f) {
  const lines = f.split("-").map(Number).filter((n) => n > 0);
  if (!lines.length) return "";
  const W = 60, H = 80, y0 = 25, y1 = 70;
  const dots = [[W / 2, 9]];
  lines.forEach((n, k) => {
    const y = lines.length === 1 ? (y0 + y1) / 2 : y0 + k * (y1 - y0) / (lines.length - 1);
    for (let i = 0; i < n; i++) dots.push([W * (i + 1) / (n + 1), y]);
  });
  return `<svg class="fm-pitch" viewBox="0 0 ${W} ${H}" aria-hidden="true">
    <rect x="1" y="1" width="${W - 2}" height="${H - 2}" rx="3" class="fm-bg"/>
    <g class="fm-lines"><line x1="1" y1="${H / 2}" x2="${W - 1}" y2="${H / 2}"/><circle cx="${W / 2}" cy="${H / 2}" r="6"/>
      <rect x="16" y="1" width="28" height="10"/><rect x="16" y="${H - 11}" width="28" height="10"/></g>
    ${dots.map(([x, y], i) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2" class="${i ? "fm-dot" : "fm-gk"}"/>`).join("")}
  </svg>`;
}

// ---- History: season by season from the club's matches since 2020. A season runs July to June,
// or the calendar year for clubs that play through the summer (MLS, Norway ...).
function clubHistoryTab() {
  const { data } = state.club;
  const rows = data?.rows || [];
  if (!rows.length) return `<div class="empty-state">No match history for this club yet.</div>`;
  const { calendar, seasonOf, label } = clubSeasons(rows);
  const bySeason = new Map();
  rows.forEach((m, i) => {
    const y = seasonOf(m);
    if (!bySeason.has(y)) bySeason.set(y, { start: i > 0 ? rows[i - 1].rank : data.start, list: [] });
    bySeason.get(y).list.push(m);
  });
  const seasons = [...bySeason].reverse().map(([y, { start, list }]) => {
    const w = list.filter((m) => m.gf > m.ga).length, d = list.filter((m) => m.gf === m.ga).length;
    const gf = list.reduce((a, m) => a + m.gf, 0), ga = list.reduce((a, m) => a + m.ga, 0);
    const end = list[list.length - 1].rank;
    const leagueCount = new Map();
    for (const m of list) if (state.data.competitions[m.league]?.type !== "Cup") leagueCount.set(m.league, (leagueCount.get(m.league) || 0) + 1);
    const lg = [...leagueCount].sort((a, b) => b[1] - a[1])[0]?.[0];
    const peak = Math.max(...list.map((m) => m.rank));
    return { y, list, w, d, l: list.length - w - d, gf, ga, start, end, peak, lg };
  });
  return `
    <div class="chart-card"><div class="chart-head"><span class="chart-title">Elo at the end of each season</span></div>
      <div class="season-bars">${seasons.slice().reverse().map((s) => {
        const lo = Math.min(...seasons.map((x) => x.end)) - 20, hi = Math.max(...seasons.map((x) => x.end));
        return `<div class="season-bar" title="${escapeHtml(`${label(s.y)}: ${s.end.toFixed(1)}`)}"><span class="sb-val">${Math.round(s.end)}</span>
          <div class="sb-fill" style="height:${Math.max(6, 100 * (s.end - lo) / (hi - lo || 1)).toFixed(0)}%"></div><span class="sb-label">${label(s.y)}</span></div>`;
      }).join("")}</div></div>
    <div class="club-section"><div class="modal-section">Season by season</div>
      <table class="season-table"><thead><tr><th>Season</th><th>League · record · goals</th><th class="num">Elo</th><th class="num">Change</th></tr></thead>
      <tbody>${seasons.map((s) => `<tr>
        <td class="num" style="text-align:left">${label(s.y)}${s.y === seasons[0].y ? `<div class="dim">so far</div>` : ""}</td>
        <td>${s.lg ? escapeHtml(SHORT_NAMES[s.lg] || state.data.competitions[s.lg]?.name || "") : `<span class="dim">Cups only</span>`}
          <div class="dim">${s.list.length} played · ${s.w}W ${s.d}D ${s.l}L · ${s.gf}–${s.ga}</div></td>
        <td class="num">${Math.round(s.end)}<div class="dim">high ${Math.round(s.peak)}</div></td>
        <td class="num">${s.start != null ? moveHtml(s.end - s.start) : ""}</td></tr>`).join("")}</tbody></table>
      <div class="page-note">Elo: the club's Elo rating after its last match of the season; change: over the season. All competitions.</div></div>`;
}

$("#club-body").addEventListener("click", (e) => {
  if (!state.club) return;
  const t = e.target.closest("[data-ctab]");
  if (t) { state.clubTab = t.dataset.ctab; return renderClubTab(); }
  const matchView = e.target.closest("[data-club-match-view]");
  if (matchView) { state.club.matchView = matchView.dataset.clubMatchView; state.club.allResults = false; return renderClubTab(); }
  if (e.target.closest("[data-club-more]")) { state.club.allResults = true; renderClubTab(); }
});

function niceTicks(lo, hi, count) {
  const step0 = (hi - lo) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || step0;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
  return out;
}

// ------------------------------------------------------------------ team modal
function openTeam(teamId) {
  const r = state.rankByTeam.get(teamId);
  $("#team-modal-title").innerHTML = `${escapeHtml(teamName(teamId))} <a class="team-link" style="font-size:12px;color:var(--blue-text);margin-left:6px" href="${clubHref(teamId)}">Club page ›</a>`;
  $("#team-modal-sub").textContent = r ? compLabel(r.league) : "";
  const games = state.data.matches.filter((m) => m.home === teamId || m.away === teamId);
  const results = games.filter((m) => FINISHED.has(m.status) && m.hg != null).reverse();
  const upcoming = games.filter((m) => !FINISHED.has(m.status) && !LIVE.has(m.status) && m.status !== "CANC").slice(0, 8);

  const row = (m, isResult) => {
    const home = m.home === teamId;
    const opp = `${home ? "" : "@ "}${teamName(home ? m.away : m.home)}`;
    let right;
    if (isResult) {
      const gf = home ? m.hg : m.ag, ga = home ? m.ag : m.hg;
      const cls = gf > ga ? "res-w" : gf === ga ? "res-d" : "res-l";
      right = `<span class="team-row-res ${cls}">${gf}–${ga}</span>`;
    } else if (m.p_home != null) {
      const win = Math.round(100 * (home ? m.p_home : m.p_away));
      right = `<span class="team-row-res">${win}% win</span>`;
    } else right = "";
    return `<div class="team-row"><span class="team-row-date">${escapeHtml(fmtShortDate(m.kickoff))}</span>
      <span class="team-row-opp" title="${escapeHtml(compLabel(m.league))}">${escapeHtml(opp)}</span>${right}</div>`;
  };

  const stat = (label, value) => `<div class="team-stat"><div class="team-stat-label">${label}</div><div class="team-stat-value">${value}</div></div>`;
  $("#team-modal-body").innerHTML = (r ? `<div class="team-stats">
      ${stat("Baseline Strength", Math.round(r.lt))}${stat("Current Strength", Math.round(r.current))}
      ${stat("Current − Baseline", formHtml(r.trend) || "–")}${stat("Last 6 matches", formHtml(r.form) || "–")}${stat("Played", r.played)}
      ${r.attack != null ? `${stat("Attack", Math.round(r.attack))}${stat("Defence", Math.round(r.defence))}${stat("Home", Math.round(r.home))}${stat("Away", Math.round(r.away))}` : ""}
    </div>` : "") +
    xiBlock(teamId) +
    (upcoming.length ? `<div class="modal-section">Next matches</div>${upcoming.map((m) => row(m, false)).join("")}` : "") +
    (results.length ? `<div class="modal-section">Recent results</div>${results.slice(0, 8).map((m) => row(m, true)).join("")}` : "");
  $("#team-modal").hidden = false;
  state.modalTeam = teamId;
  // the predicted XI comes from players.json: drawn again with it if the pop-up is still on this club
  if (state.players === undefined)
    loadPlayers().then(() => { if (!$("#team-modal").hidden && state.modalTeam === teamId) openTeam(teamId); });
}

// ------------------------------------------------------------------ player page
const GROUP_OF = { GK: "GK", CB: "CB", LB: "FB", RB: "FB", LWB: "FB", RWB: "FB", DM: "DM", CM: "CM", LM: "W", RM: "W",   // as positions.py
                   AM: "AM", LW: "W", RW: "W", ST: "ST", G: "GK", D: "CB", M: "CM", F: "ST" };
const GROUP_NAME = { GK: "goalkeepers", CB: "centre-backs", FB: "full-backs", DM: "defensive mids", CM: "central mids",
                     AM: "attacking mids", W: "wingers", ST: "strikers" };
const seasonShort = (y) => `${String(y).slice(2)}/${String(y + 1).slice(2)}`;
const seasonName = (y) => `${y}/${String(y + 1).slice(2)}`;
function playerById(id) {
  return (state.playersById ||= new Map(state.players.list.map((x) => [String(x.id), x]))).get(String(id));
}
const playerPages = new Map();     // player id -> his page file (data/players/<id>.json)
async function openPlayerPage(id) {
  showPage();
  state.club = null;
  const body = $("#club-body");
  if (state.players === undefined) {
    body.innerHTML = `<div class="empty-state">Loading…</div>`;
    await loadPlayers();
    if (location.hash !== `#/player/${id}`) return;      // moved on while loading
  }
  const p = state.players && playerById(id);
  if (!p) { body.innerHTML = loadFailed("players") ? loadError("the players") : `<div class="empty-state">This player isn't in the current ranks.</div>`; return; }
  setTitle(p.name);
  body.innerHTML = `<div class="empty-state">Loading ${escapeHtml(p.name)}…</div>`;
  if (!playerPages.has(id)) {
    const d = await getJsonOrNull(`data/players/${id}.json`);
    if (d) playerPages.set(id, { ...d, seasonRows: rowsToObjects(d.season_fields, d.seasons), matchRows: rowsToObjects(d.match_fields, d.matches) });
  }
  const page = playerPages.get(id) || null;
  if (!page?.positions) { loadPlayerSeasons(); await state.playerSeasonsLoading; }   // no page file, or an older one
  if (location.hash !== `#/player/${id}`) return;      // moved on while loading
  state.player = { p, page, detail: playerDetail(p, page), season: null };
  renderPlayerPage();
}
// His season detail (birth date, clubs by season, starting minutes by position): from his page
// file, else his rows of player_seasons.json
function playerDetail(p, page) {
  if (page?.positions) return { born: page.born, spells: page.spells || {}, positions: page.positions };
  const d = state.playerSeasons, k = String(p.id);
  return { born: d?.born?.[k], spells: d?.players?.[k] || {}, positions: d?.positions?.[k] || {} };
}
const POS_WORD = { G: "GK", D: "DEF", M: "MID", F: "FWD", SUB: "Sub" };
const GROUP_SINGLE = { GK: "goalkeeper", CB: "centre-back", FB: "full-back", DM: "defensive mid", CM: "central mid",
                       AM: "attacking mid", W: "winger", ST: "striker" };
// The group a season is rated as: the role group with most starting minutes that season (as
// the model does); starts without a line-up position only if there's nothing else
function seasonGroup(list) {
  const by = new Map();
  for (const [r, m] of list || []) if (!POS_WORD[r] && GROUP_OF[r]) by.set(GROUP_OF[r], (by.get(GROUP_OF[r]) || 0) + m);
  if (!by.size) for (const [r, m] of list || []) if (GROUP_OF[r]) by.set(GROUP_OF[r], (by.get(GROUP_OF[r]) || 0) + m);
  return by.size ? [...by].sort((a, b) => b[1] - a[1])[0][0] : null;
}
// [[role, minutes], ...] -> "LB 84% · LWB 16%": shares of his starting minutes (minutes off the
// bench have no position and aren't counted; positions under 3% grouped as "other")
function positionShares(list) {
  list = list.filter(([r]) => r !== "SUB");
  const total = list.reduce((a, [, m]) => a + m, 0);
  if (!total) return "";
  const shown = list.filter(([, m]) => m / total >= 0.03);
  const other = total - shown.reduce((a, [, m]) => a + m, 0);
  return shown.map(([r, m]) => `<span class="pos-share${r === "SUB" ? " sub" : ""}">${escapeHtml(POS_WORD[r] || r)} ${Math.round(100 * m / total)}%</span>`).join("")
    + (other > 0 ? `<span class="pos-share sub">other ${Math.round(100 * other / total)}%</span>` : "");
}

// Match ratings (API-Football, 0-10): coloured like the rank chips
const ratingTier = (r) => r >= 7.5 ? 4 : r >= 7 ? 3 : r >= 6.5 ? 2 : 1;
const ratingChip = (r) => r == null ? `<span class="rel-chip rating-none">–</span>` : `<span class="rel-chip rel-${ratingTier(r)}">${r.toFixed(1)}</span>`;
const pageTeamName = (id) => state.player?.page?.teams?.[id] || state.playerSeasons?.teams?.[id] || teamName(id);
const PLAYER_TABS = [["overview", "Overview"], ["stats", "Stats"], ["matches", "Matches"], ["career", "Career"]];

function renderPlayerPage() {
  const { p } = state.player;
  const born = state.player.detail.born;
  const league = p.team && p.league ? SHORT_NAMES[p.league] || state.data.competitions[p.league]?.name : "";
  const tab = state.playerTab || "overview";
  $("#club-body").innerHTML = `
    <div class="pl-hero">
      ${personChip(p.name, "player-photo-lg")}
      <div class="pl-hero-main">
        <h2>${escapeHtml(p.name)}</h2>
        <div class="pl-hero-club">${p.team ? clubCrest(p.team, "club-logo", `data-club="${p.team}"`) : ""}
          <span>${playerClub(p)}${league ? `<span class="dim-sep"> · </span><a class="pl-league team-link" href="${leagueHref(p.league)}">${escapeHtml(league)}</a>` : ""}</span></div>
        <div class="pl-hero-club pl-hero-nat">${p.nationality ? `${flagImg(p.nationality)}<span>${natLink(p.nationality)}</span><span class="dim-sep">·</span>` : ""}
          <span class="pl-meta">${escapeHtml(p.position || "")}</span>${p.age != null ? `<span class="dim-sep">·</span>
          <span class="pl-meta"${born ? ` title="Born ${escapeHtml(parseDateInput(born).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }))}"` : ""}>${p.age}</span>` : ""}</div>
      </div>
      <div class="hero-ranks">${heroGoalsAssists(p)}
        <div class="pl-hero-rank rel-${rankTier(p.rank)}" title="${escapeHtml(ABILITY_TIP)}">
        <span class="val">${Math.round(p.rank)}</span><span class="lbl">Ability</span></div></div>
    </div>
    ${playerKeyFigures(p)}
    ${playerRecentSection()}
    <div class="page-tabs" role="tablist">${PLAYER_TABS.map(([k, label]) =>
      `<button type="button" role="tab" data-ptab="${k}" aria-selected="${k === tab}">${label}</button>`).join("")}</div>
    <div id="pl-tab"></div>`;
  renderPlayerTab();
}

// This season's league goals and assists (all his clubs), first thing on his page
function heroGoalsAssists(p) {
  const now = playerSeasonNow(p, state.player?.page);
  const y = state.players.seasons?.[0];
  const tip = `League ${y != null ? seasonName(y) : "this season"}, all his clubs`;
  const badge = (v, lbl) => `<div class="pl-hero-rank pl-hero-ga" title="${escapeHtml(tip)}"><span class="val">${v ?? (now ? 0 : "–")}</span><span class="lbl">${lbl}</span></div>`;
  return badge(now?.goals, "Goals") + badge(now?.assists, "Assists");
}

const ABILITY_TIP = "Underlying Ability (0-100): the model's estimate of his level, from his clubs' strength, his stats against players in his position and his age curve. It carries over from earlier seasons, so it isn't a measure of current form: Current Season and Recent Performance are shown separately";

// His league minutes and stats this season (all his clubs), from his page file, else the
// Players view's season detail (minutes, rating, goals and assists only)
function playerSeasonNow(p, page) {
  const y = state.players.seasons?.[0];
  if (y == null) return null;
  if (page?.seasonRows) {
    const s = sumSeason(page.seasonRows.filter((r) => r.season === y));
    return s ? { ...s, full: true } : { minutes: 0, full: true };
  }
  const sp = state.player?.detail?.spells?.[String(y)];
  if (!sp) return null;
  const minutes = sp.reduce((a, x) => a + (x[1] || 0), 0);
  const rated = sp.filter((x) => x[3] != null && x[1]);
  return { minutes, goals: sp.reduce((a, x) => a + (x[4] || 0), 0), assists: sp.reduce((a, x) => a + (x[5] || 0), 0),
    rating: rated.length ? rated.reduce((a, x) => a + x[3] * x[1], 0) / rated.reduce((a, x) => a + x[1], 0) : null, full: false };
}
// His latest league appearance in the page file, and whether it falls in this season's window
function lastAppearance(page) {
  const m = page?.matchRows?.[0];
  return m ? { m, days: daysSince(m.date) } : null;
}

function playerKeyFigures(p) {
  const list = state.players.list;
  const inLeague = p.team && p.league ? list.filter((x) => x.team && x.league === p.league) : [];
  const leaguePlace = inLeague.filter((x) => x.rank > p.rank).length + 1;
  const league = p.league ? SHORT_NAMES[p.league] || state.data.competitions[p.league]?.name || "" : "";
  const page = state.player?.page;
  const now = playerSeasonNow(p, page);
  const y = state.players.seasons?.[0];
  const tier = (place, of) => { const s = place / Math.max(1, of); return s <= 0.02 ? 4 : s <= 0.1 ? 3 : s <= 0.35 ? 2 : 1; };
  const season = y != null ? seasonShort(y) : "Season";

  // first row: his league rank, then this season's minutes and match rating
  const main = (inLeague.length ? kfTile("League rank", `#${leaguePlace.toLocaleString()}`, `of ${inLeague.length.toLocaleString()} in ${escapeHtml(league)}`,
      `Place by Ability among ranked players at ${league} clubs`, tier(leaguePlace, inLeague.length)) : "")
    + kfTile(`${season} minutes`, now ? now.minutes.toLocaleString() : "–",
      now?.apps != null ? `${now.apps} apps${now.starts != null ? ` · ${now.starts} started` : ""}` : "league matches",
      "League minutes this season, all his clubs")
    + kfTile(`${season} match rating`, now?.rating != null ? now.rating.toFixed(2) : "–", now?.minutes ? "season average" : "no minutes yet",
      "API-Football's match rating, averaged over his league minutes this season");

  return `<div class="key-figures pl-figures"><div class="kf-group"><div class="kf-tiles kf-main">${main}</div></div></div>`;
}

function renderPlayerTab() {
  const tab = state.playerTab || "overview";
  document.querySelectorAll("#club-body [data-ptab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.ptab === tab)));
  const el = $("#pl-tab");
  el.innerHTML = tab === "stats" ? playerStatsTab() : tab === "matches" ? playerMatchesTab()
    : tab === "career" ? playerCareerTab() : playerOverviewTab();
  if (tab === "career") drawPlayerChart($("#pl-chart"));
}

const plTile = (label, value, sub = "") => `<div class="team-stat"><div class="team-stat-label">${label}</div><div class="team-stat-value">${value}</div>${sub ? `<div class="team-stat-sub">${sub}</div>` : ""}</div>`;
const plSection = (title, body, note = "") => `<div class="club-section pl-block">${title ? `<div class="modal-section">${title}</div>` : ""}${body}${note ? `<div class="page-note">${note}</div>` : ""}</div>`;

// ---- Recent Performance, above the tabs: his latest appearances, dated so old ones aren't read as form
const RECENT_DAYS = 45;        // latest appearance older than this: not shown as recent form
function playerRecentSection() {
  const { page } = state.player;
  const last = lastAppearance(page);
  const stale = !last || last.days > RECENT_DAYS;
  const apps = (page?.matchRows || []).slice(0, 10);
  if (!apps.length) return plSection("Recent Performance", `<div class="pl-callout">No match-by-match data for him: only the leagues with per-match player stats have it.</div>`);
  return plSection(stale ? `Most recent appearances · last played ${escapeHtml(fmtLongDate(last.m.date))}` : "",
    `${stale ? `<div class="pl-callout">No league appearance for ${last.days} days, so these are not current form.</div>` : ""}
    <div class="form-strip">${apps.map((m) => `<div class="form-cell" title="${escapeHtml(`${fmtShortDate(m.date)} ${m.home ? "v" : "@"} ${pageTeamName(m.opponent)} ${m.gf}–${m.ga} · ${m.minutes}′${m.goals ? ` · ${m.goals} G` : ""}${m.assists ? ` · ${m.assists} A` : ""}`)}">
      ${ratingChip(m.rating)}${gaIcons(m)}</div>`).join("")}</div>`);
}
// Under each match: a ball per goal and a boot per assist (a count past three, so the cell stays narrow)
const gaIcons = (m) => {
  const icons = (n, icon, word) => !n ? "" : `<span class="ga-icon" title="${n} ${word}${n === 1 ? "" : "s"}">${n > 3 ? `${icon}×${n}` : icon.repeat(n)}</span>`;
  return `<span class="form-ga">${icons(m.goals, "⚽", "goal")}${icons(m.assists, "👟", "assist")}</span>`;
};

// ---- Overview: next match beside his positions, then Current Season (this season's league play)
function playerOverviewTab() {
  const { p, page } = state.player;
  const seasons = state.players.seasons || [];
  const y = seasons[0];
  const now = playerSeasonNow(p, page);
  const injury = page?.injury;
  const gk = GROUP_OF[p.position] === "GK";

  // Current Season: this season's league play, or plainly none
  let seasonBody;
  if (now?.minutes) {
    seasonBody = `<div class="team-stats compact">
        ${plTile("Minutes", now.minutes.toLocaleString(), now.apps != null ? `${now.apps} apps${now.starts != null ? ` · ${now.starts} started` : ""}` : "")}
        ${gk ? plTile("Saves", now.saves ?? "–") : plTile("Goals", now.goals ?? "–")}
        ${gk ? plTile("Conceded", now.conceded ?? "–") : plTile("Assists", now.assists ?? "–")}
        ${plTile("Match rating", now.rating != null ? now.rating.toFixed(2) : "–")}
      </div>`;
  } else {
    seasonBody = `<div class="pl-callout">No league minutes in ${y != null ? seasonName(y) : "this season"} yet${
      injury ? ` · listed ${availabilityWord(injury).toLowerCase()}` : ""}.
      His Ability of ${Math.round(p.rank)} comes from earlier seasons and his age curve, not from current form.</div>`;
  }
  const seasonNote = now?.minutes && now.minutes < 900
    ? `Only ${now.minutes.toLocaleString()} minutes so far: this season moves his Ability only a little until he plays more.`
    : now && !now.full ? "Season totals only: this league has no match-by-match player data." : "";
  const current = plSection(`Current Season · ${y != null ? seasonName(y) : ""}`, seasonBody, seasonNote);

  return `
    ${nextMatchCard()}${positionRow(p)}
    ${current}`;
}
const resClass = (m) => m.gf > m.ga ? "res-w" : m.gf === m.ga ? "res-d" : "res-l";

// His positions in a row, most played first (his share of starting minutes; then best rank): his rank in each role group he has one in (his recent
// stats scored as that position, so LB and RB share the full-back rank) and his share of starting
// minutes there. Keepers have no position_ranks: their keeper rank is their rank.
function positionRow(p) {
  const pos = state.player.detail.positions;
  const group = GROUP_OF[p.position];
  const rankIn = (g) => p.position_ranks?.[g] ?? (g === group ? p.rank : null);
  const ranked = Object.keys(GROUP_NAME).filter((g) => rankIn(g) != null);
  if (!ranked.length) return "";
  const period = pos["12m"] ? "12m" : "all";
  const rows = (pos[period] || []).filter(([r]) => r !== "SUB");
  const total = rows.reduce((a, [, m]) => a + m, 0);
  const mins = {};
  for (const [r, m] of rows) if (GROUP_OF[r]) mins[GROUP_OF[r]] = (mins[GROUP_OF[r]] || 0) + m;
  const share = (g) => total ? Math.round(100 * (mins[g] || 0) / total) : 0;
  const groups = ranked.sort((a, b) => (mins[b] || 0) - (mins[a] || 0) || rankIn(b) - rankIn(a));
  const chips = groups.map((g) => {
    const rank = rankIn(g), pct = share(g);
    return `<div class="pos-chip rel-${rankTier(rank)}${g === group ? " main" : ""}"
        title="${GROUP_SINGLE[g]}: rank ${rank.toFixed(1)} · ${pct ? `${pct}% of his starting minutes` : "no starts here"}">
      <span class="pos-chip-pos">${g}</span><span class="pos-chip-rank">${Math.round(rank)}</span>
      <span class="pos-chip-pct">${pct ? `${pct}%` : "–"}</span></div>`;
  }).join("");
  return `<div class="club-section pos-section">
    <div class="pos-row">${chips}</div>
  </div>`;
}

// His club's next match: when, who, the model's view, and whether he's expected to play
function nextMatchCard() {
  const { p, page } = state.player;
  if (!p.team) return "";
  const m = state.data.matches.find((x) => (x.home === p.team || x.away === p.team)
    && !FINISHED.has(x.status) && !["CANC", "PST", "ABD"].includes(x.status));
  if (!m) return "";
  const home = m.home === p.team, opp = home ? m.away : m.home;
  const xi = state.players.nextXi?.[String(p.team)];
  const xiHere = xi && xi.fixture === m.id;
  const inXi = xiHere && xi.players.find(([pid]) => pid === p.id);
  const inj = page?.injury;                      // [fixture, type, ban]
  const status = inj && inj[0] === m.id
    ? [inj[1] === "Questionable" ? "warn" : "bad", availabilityWord(inj)]
    : inXi ? ["good", `In the predicted XI${inXi[2] ? ` as ${inXi[2]}` : ""}`]
    : xiHere ? ["muted", "Not in the predicted XI"] : null;
  const win = m.p_home != null ? Math.round(100 * (home ? m.p_home : m.p_away)) : null;
  const proj = m.home_xg != null ? `${(home ? m.home_xg : m.away_xg).toFixed(1)}–${(home ? m.away_xg : m.home_xg).toFixed(1)}` : "";
  return `<div class="next-card">
    <div class="next-top"><span class="next-label">${LIVE.has(m.status) ? "Live now" : "Next match"}</span>
      <span>${escapeHtml(fmtDay(m.kickoff))} · ${escapeHtml(fmtTime(m.kickoff))}</span></div>
    <div class="next-opp">${clubCrest(opp, "club-logo", `data-club="${opp}"`)}
      <span class="next-opp-name">${home ? "v" : "@"} ${clubLink(opp)}</span></div>
    <div class="next-meta"><span>${escapeHtml(compLabel(m.league))}</span>${win != null ? `<span>${win}% win</span>` : ""}${proj ? `<span>projected ${proj}</span>` : ""}</div>
    ${status ? `<div class="next-status ${status[0]}">${escapeHtml(status[1])}</div>` : ""}
  </div>`;
}

// Season rank line chart (Career tab), drawn to the width of its box (so text stays readable on phones)
function drawPlayerChart(wrap) {
  if (!wrap) return;
  const { p } = state.player;
  const seasons = state.players.seasons || [];
  const pts = seasons.map((y, k) => ({ y, v: p.seasons?.[k], est: p.estimated?.includes(k) })).filter((d) => d.v != null).reverse()
    .map((d) => ({ label: seasonShort(d.y), v: d.v, est: d.est, tip: `${seasonName(d.y)}<br>Rank <b>${d.v.toFixed(1)}</b>${d.est ? "<br>estimated" : ""}` }));
  const W = Math.max(260, wrap.clientWidth), H = 180, L = 30, R = 14, T = 20, B = 22;
  let lo = Math.min(...pts.map((d) => d.v)), hi = Math.max(...pts.map((d) => d.v));
  const pad = Math.max(3, (hi - lo) * 0.15); lo = Math.max(0, lo - pad); hi = Math.min(100, hi + pad);
  const IN = 12;
  const x = (i) => L + IN + (pts.length === 1 ? 0.5 : i / (pts.length - 1)) * (W - L - R - 2 * IN);
  const y = (v) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
  const every = Math.max(1, Math.ceil(pts.length * 46 / (W - L - R)));     // x labels that fit
  const showLabel = (i) => i === pts.length - 1 || (i % every === 0 && pts.length - 1 - i >= every);
  const few = pts.length <= 8;
  wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${escapeHtml(p.name)} rank, ${Math.round(pts[0].v)} to ${Math.round(pts[pts.length - 1].v)}">
      <g class="chart-grid">${niceTicks(lo, hi, 4).map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/>`).join("")}</g>
      <g class="chart-axis">${niceTicks(lo, hi, 4).map((v) => `<text x="${L - 6}" y="${(y(v) + 3).toFixed(1)}" text-anchor="end">${Math.round(v)}</text>`).join("")}
        ${pts.map((d, i) => showLabel(i) ? `<text x="${x(i).toFixed(1)}" y="${H - 6}" text-anchor="middle">${escapeHtml(d.label)}</text>` : "").join("")}</g>
      <path class="chart-line" d="${pts.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.v).toFixed(1)}`).join("")}"/>
      ${pts.map((d, i) => few || d.now ? `<circle class="season-dot${d.est ? " est" : ""}" cx="${x(i).toFixed(1)}" cy="${y(d.v).toFixed(1)}" r="4.5"/>
        ${few ? `<text class="season-label" x="${x(i).toFixed(1)}" y="${(y(d.v) - 9).toFixed(1)}" text-anchor="middle">${Math.round(d.v)}</text>` : ""}` : "").join("")}
      <line class="chart-cross" data-c="cross" y1="${T}" y2="${H - B}" visibility="hidden"/>
      <circle class="chart-dot" data-c="dot" r="4.5" visibility="hidden"/>
      <rect x="${L}" y="0" width="${W - L - R}" height="${H}" fill="transparent" data-c="hit"/>
    </svg><div class="chart-tip" data-c="tip" hidden></div>`;
  const [hit, cross, dot, tip] = ["hit", "cross", "dot", "tip"].map((c) => wrap.querySelector(`[data-c="${c}"]`));
  const show = (evt) => {
    const rect = hit.getBoundingClientRect();
    const px = (evt.clientX - rect.left) / rect.width * (W - L - R) + L;
    let i = 0;
    pts.forEach((d, j) => { if (Math.abs(x(j) - px) < Math.abs(x(i) - px)) i = j; });
    const cx = x(i), cy = y(pts[i].v);
    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
    dot.setAttribute("cx", cx); dot.setAttribute("cy", cy); dot.setAttribute("visibility", "visible");
    tip.innerHTML = pts[i].tip;
    tip.hidden = false;
    const tw = tip.offsetWidth;
    tip.style.left = `${Math.min(Math.max(cx - tw / 2, 0), wrap.clientWidth - tw)}px`;
    tip.style.top = `${Math.max(0, cy - tip.offsetHeight - 12)}px`;
  };
  const hide = () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); };
  hit.addEventListener("pointermove", show);
  hit.addEventListener("pointerdown", show);
  hit.addEventListener("pointerleave", hide);
}
window.addEventListener("resize", () => { if (state.player) drawPlayerChart($("#pl-chart")); });

// ---- Stats: one season (all his clubs added up), as totals or per 90 minutes
const SUM_KEYS = ["apps", "starts", "minutes", "goals", "assists", "shots_on", "key_passes", "passes", "tackles",
                  "interceptions", "blocks", "duels_won", "duels", "dribbles_won", "fouls", "yellow", "red", "saves", "conceded"];
// a season's lines added up (null where no line has the stat); rating weighted by minutes,
// pass accuracy by passes
function sumSeason(rows) {
  if (!rows.length) return null;
  const out = {};
  for (const k of SUM_KEYS) {
    const vs = rows.map((r) => r[k]).filter((v) => v != null);
    out[k] = vs.length ? vs.reduce((a, b) => a + b, 0) : null;
  }
  const wavg = (key, weight) => {
    const rs = rows.filter((r) => r[key] != null && r[weight]);
    return rs.length ? rs.reduce((a, r) => a + r[key] * r[weight], 0) / rs.reduce((a, r) => a + r[weight], 0) : null;
  };
  out.rating = wavg("rating", "minutes");
  out.pass_acc = wavg("pass_acc", "passes");
  return out;
}
const STAT_GROUPS = [
  ["Goalkeeping", [["saves", "Saves"], ["conceded", "Goals conceded"], ["save_pct", "Save %", "pct"]]],
  ["Attacking", [["goals", "Goals"], ["assists", "Assists"], ["shots_on", "Shots on target"], ["key_passes", "Key passes"],
                 ["dribbles_won", "Dribbles won"]]],
  ["Passing", [["passes", "Passes"], ["pass_acc", "Pass accuracy", "pct"]]],
  ["Defending", [["tackles", "Tackles"], ["interceptions", "Interceptions"], ["blocks", "Blocks"], ["duels_won", "Duels won"],
                 ["duel_pct", "Duels won %", "pct"]]],
  ["Discipline", [["fouls", "Fouls"], ["yellow", "Yellow cards"], ["red", "Red cards"]]],
];
function playerStatsTab() {
  const { p, page } = state.player;
  if (!page?.seasonRows.length) return `<div class="empty-state">No season stats for him yet.</div>`;
  const years = [...new Set(page.seasonRows.map((r) => r.season))].sort((a, b) => b - a);
  const year = years.includes(state.player.season) ? state.player.season : years[0];
  const rows = page.seasonRows.filter((r) => r.season === year);
  const s = sumSeason(rows);
  s.save_pct = s.saves != null && s.saves + (s.conceded || 0) ? 100 * s.saves / (s.saves + (s.conceded || 0)) : null;
  s.duel_pct = s.duels ? 100 * s.duels_won / s.duels : null;
  const per90 = !!state.playerPer90 && s.minutes > 0;
  const fmt = (k, kind) => {
    const v = s[k];
    if (v == null) return "–";
    if (kind === "pct") return `${Math.round(v)}%`;
    return per90 ? (v * 90 / s.minutes).toFixed(2) : v.toLocaleString();
  };
  const gk = GROUP_OF[p.position] === "GK";
  const groups = STAT_GROUPS.filter(([name]) => gk ? name !== "Attacking" : name !== "Goalkeeping");
  const tile = (label, value, sub = "") => `<div class="team-stat"><div class="team-stat-label">${label}</div><div class="team-stat-value">${value}</div>${sub ? `<div class="team-stat-sub">${sub}</div>` : ""}</div>`;
  const partial = rows.some((r) => r.starts == null);
  return `
    <div class="stats-controls">
      <div class="chip-scroll">${years.map((y) => `<button type="button" class="filter-chip" data-pseason="${y}" aria-pressed="${y === year}">${seasonShort(y)}</button>`).join("")}</div>
      <div class="seg">${[["0", "Totals"], ["1", "Per 90"]].map(([k, l]) =>
        `<button type="button" data-per90="${k}" aria-pressed="${String(per90) === (k === "1" ? "true" : "false")}">${l}</button>`).join("")}</div>
    </div>
    <div class="season-clubs">${rows.map((r) => `<div class="season-club">${clubCrest(r.team, "club-logo", `data-club="${r.team}"`)}
      ${clubLink(r.team, pageTeamName(r.team))}<span class="dim"> · ${escapeHtml(compLabel(r.league))} · ${r.apps} apps · ${r.minutes.toLocaleString()}′</span></div>`).join("")}</div>
    <div class="team-stats compact">
      ${tile("Apps", s.apps, s.starts != null && !partial ? `${s.starts} started` : "")}
      ${tile("Minutes", s.minutes.toLocaleString())}
      ${tile("Match rating", s.rating != null ? s.rating.toFixed(2) : "–")}
      ${gk ? tile("Saves", fmt("saves")) : tile("Goals", fmt("goals"))}
      ${gk ? tile("Save %", fmt("save_pct", "pct")) : tile("Assists", fmt("assists"))}
    </div>
    <div class="stat-groups">${groups.map(([name, items]) => `<div class="stat-group"><div class="stat-group-title">${name}</div>
      ${items.map(([k, label, kind]) => `<div class="stat-line"><span>${label}</span><b>${fmt(k, kind)}</b></div>`).join("")}</div>`).join("")}</div>
    <div class="page-note">League matches only${per90 ? `, per 90 minutes (${s.minutes.toLocaleString()} minutes)` : ""}.${partial ? " Leagues without match-by-match data give season totals only, so starts and pass accuracy are missing there." : ""}</div>`;
}

// ---- Matches: his last league appearances, newest first
function playerMatchesTab() {
  const { page } = state.player;
  if (!page?.matchRows.length) return `<div class="empty-state">No match-by-match data for him (only the leagues with per-match player stats have it).</div>`;
  const gk = GROUP_OF[state.player.p.position] === "GK";
  const row = (m) => {
    const bits = [
      `${m.minutes}′${m.started ? "" : " off the bench"}`, m.started && m.role ? POS_WORD[m.role] || m.role : "",
      m.goals ? `${m.goals} goal${m.goals > 1 ? "s" : ""}` : "", m.assists ? `${m.assists} assist${m.assists > 1 ? "s" : ""}` : "",
      gk ? `${m.saves} save${m.saves === 1 ? "" : "s"}` : m.key_passes ? `${m.key_passes} key pass${m.key_passes > 1 ? "es" : ""}` : "",
      !gk && m.shots_on ? `${m.shots_on} on target` : "", m.duels ? `duels ${m.duels_won}/${m.duels}` : "",
      m.red ? `<span class="card red"></span>` : m.yellow ? `<span class="card"></span>` : "",
    ].filter(Boolean);
    return `<div class="match-row">
      <div class="mr-date">${escapeHtml(fmtShortDate(m.date))}</div>
      <div class="mr-opp">${clubCrest(m.opponent, "club-logo", `data-club="${m.opponent}"`)}
        <span>${m.home ? "v" : "@"} ${clubLink(m.opponent, pageTeamName(m.opponent))}</span></div>
      <div class="mr-res ${resClass(m)}">${m.gf}–${m.ga}</div>
      <div class="mr-rating">${ratingChip(m.rating)}</div>
      <div class="mr-sub"><span>${bits.join(" · ")}</span>${m.rank != null ? `<span class="mr-rank">rank ${Math.round(m.rank)}</span>` : ""}</div>
    </div>`;
  };
  return `<div class="match-list">${page.matchRows.map(row).join("")}</div>
    <div class="page-note">His last ${page.matchRows.length} league appearances. Rating: API-Football's match rating. Rank: his rank going into the match.</div>`;
}

// ---- Career: rank by season with his clubs, and the clubs his current rank is built on
function playerCareerTab() {
  const { p } = state.player;
  const seasons = state.players.seasons || [];
  const hasSeasons = seasons.filter((y, k) => p.seasons?.[k] != null).length >= 2;
  const { spells: detail, positions: posBySeason } = state.player.detail;
  const spellHtml = (sp) => sp.map(([team, mins, clubRank, rating, goals, assists]) =>
    `<div class="spell">${clubLink(team, pageTeamName(team))}
      <span class="dim"> · club ${clubRank ?? "–"} · ${mins ? `${mins.toLocaleString()}′` : "no minutes here"}${rating != null ? ` · rating ${rating.toFixed(2)}` : ""}${mins ? ` · ${goals} G, ${assists} A` : ""}</span></div>`).join("");
  const rows = seasons.map((y, k) => {
    const v = p.seasons?.[k];
    if (v == null) return "";
    const est = p.estimated?.includes(k);
    const age = p.age != null ? p.age - (seasons[0] - y) : null;
    const sp = detail[String(y)] || [];
    const pos = posBySeason[String(y)];
    return `<tr><td class="num" style="text-align:left">${seasonShort(y)}<div class="dim">${age != null ? `age ${age}` : ""}</div></td>
      <td>${sp.length ? spellHtml(sp) : `<span class="dim">${est ? "Estimated from his other seasons and age" : ""}</span>`}${pos ? `<div class="pos-shares">${positionShares(pos)}${seasonGroup(pos) ? `<span class="rated-as">rated as ${GROUP_SINGLE[seasonGroup(pos)]}</span>` : ""}</div>` : ""}</td>
      <td class="num">${est ? `<span class="est">${rankChipSmall(v)}</span>` : rankChipSmall(v)}</td></tr>`;
  }).join("");
  const now = detail.now || [];
  return `
    ${hasSeasons ? `<div class="chart-card"><div class="chart-head"><span class="chart-title">Season ranks</span></div>
      <div class="chart-wrap" id="pl-chart"></div></div>` : ""}
    <div class="club-section"${hasSeasons ? "" : ' style="margin-top:0"'}><div class="modal-section">Season by season</div>
      <table class="season-table"><thead><tr><th>Season</th><th>Clubs · club Elo · minutes · rating · goals, assists</th><th class="num">Rank</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="page-note">A season's rank starts from his clubs' level (LT ALGO over his matches) and his stats against players in his position, then follows the typical age curve for his position from a level of his own: a season only moves off that curve as far as its minutes justify. Outlined ranks are estimated.</div>
    </div>
    ${now.length ? `<div class="club-section"><div class="modal-section">His current rank is built on · last 20 appearances</div><div class="season-now">${spellHtml(now)}</div></div>` : ""}`;
}
// A league name on a page opens the Rankings tab on that league's club table
$("#club-body").addEventListener("click", (e) => {
  const a = e.target.closest("[data-league]");
  if (!a) return;
  e.preventDefault();
  history.pushState(null, "", location.pathname + location.search);
  showTab("table");
  state.tableFilter = a.dataset.league;
  state.tableSearch = "";
  $("#table-search").value = "";
  if (state.tableView !== "clubs") setTableView("clubs");
  else { renderTableFilters(); renderTable(); }
  window.scrollTo(0, 0);
});
// The "#3" by the coach on a club page opens the Rankings tab in the order that place counts in (Baseline
// Strength, or the link's data-rank-sort), scrolled to the club; a club outside this season's leagues
// is searched for instead
$("#club-body").addEventListener("click", (e) => {
  const a = e.target.closest("[data-rank-team]");
  if (!a) return;
  e.preventDefault();
  const team = Number(a.dataset.rankTeam);
  history.pushState(null, "", location.pathname + location.search);
  showTab("table");
  state.tableFilter = "all";
  state.tableSort = a.dataset.rankSort || "lt";
  state.excluded = new Set();
  state.tableSearch = state.rankByTeam.get(team)?.in_league ? "" : teamName(team);
  $("#table-search").value = state.tableSearch;
  if (state.tableView !== "clubs") setTableView("clubs");
  else { renderTableFilters(); renderTable(); }
  window.scrollTo(0, 0);
  const tr = document.querySelector(`#table-wrap tr[data-team="${team}"]`);
  if (tr) { tr.classList.add("row-hl"); tr.scrollIntoView({ block: "center" }); }
});
$("#club-body").addEventListener("click", (e) => {
  const b = e.target.closest("[data-ptab], [data-pseason], [data-per90]");
  if (!b || !state.player) return;
  if (b.dataset.ptab) state.playerTab = b.dataset.ptab;
  if (b.dataset.pseason) state.player.season = Number(b.dataset.pseason);
  if (b.dataset.per90) state.playerPer90 = b.dataset.per90 === "1";
  renderPlayerTab();
});

// ------------------------------------------------------------------ nationality page
// Overview: the nationality's ranked club players. Formations and Players: the national team's
// matches, line-ups and stat lines from API-Football (data/nations/<team id>.json, nations.py),
// found through the ranking (loaded for the Elo in the corner anyway).
const NATION_TABS = [["overview", "Overview"], ["xi", "Predicted XI"], ["formations", "Formations"], ["players", "Players"]];
async function openNationPage(nat) {
  showPage(nat);
  state.club = null;
  if (state.players === undefined) {
    const at = location.hash;
    $("#club-body").innerHTML = `<div class="empty-state">Loading ${escapeHtml(nat)}…</div>`;
    await loadPlayers();
    if (location.hash !== at) return;                    // moved on while loading
  }
  const list = (state.players?.list || []).filter((p) => p.nationality === nat).sort((a, b) => b.rank - a.rank);
  state.nation = { name: nat, list, team: undefined, allPlayers: false };
  renderNationPage();
  fillNationRating(nat);
  await loadNations();
  const n = state.nations && nationFor(state.nations, nat);
  const [team] = await Promise.all([n?.team_id ? getJsonOrNull(`data/nations/${n.team_id}.json`) : null,
    state.injuries ? null : getJsonOrNull("data/injuries.json").then((d) => { state.injuries ||= d; })]);
  if (state.nation?.name !== nat) return;              // moved on while it loaded
  if (team) {           // names as API-Football sent them: some HTML-encoded ("O&apos;Reilly"), as in players.json
    for (const pid in team.players) team.players[pid] = decodeEntities(team.players[pid]);
    if (team.coach) team.coach.name = decodeEntities(team.coach.name);
    team.matchRows = rowsToObjects(team.match_fields, team.matches)
      .map((m, i) => ({ ...m, opp: decodeEntities(m.opp), coach: decodeEntities(m.coach), tournament: decodeEntities(m.tournament), i, xi: [] }));
    team.appRows = rowsToObjects(team.app_fields, team.apps);
    for (const a of team.appRows) if (a.started) team.matchRows[a.match].xi.push(a);
  }
  state.nation.team = team || null;
  $("#nat-coach").innerHTML = nationCoachHtml();
  renderNationTab();
}
// The head coach under the nation's name: his initials and name, once the team's file has loaded
function nationCoachHtml() {
  if (!state.nation?.team?.matchRows?.length) return "";
  const spell = nationSpell();
  if (!spell.coach) return "";
  return `<div class="pl-hero-club pl-hero-nat">${personChip(spell.coach, "player-photo coach-photo")}<span class="pl-meta" title="Head coach">${escapeHtml(spell.coach)}</span></div>`;
}

function renderNationPage() {
  const { name } = state.nation;
  const tab = state.nationTab || "overview";
  $("#club-body").innerHTML = `
    <div class="pl-hero">
      ${FLAG_CODES[name] ? `<img class="country-flag-lg" src="https://flagcdn.com/w160/${FLAG_CODES[name]}.png" alt="">` : "<span></span>"}
      <div class="pl-hero-main">
        <h2>${escapeHtml(name)}</h2>
        <div id="nat-coach">${nationCoachHtml()}</div>
      </div>
      <div id="nat-elo" data-nat="${escapeHtml(name)}"></div>
    </div>
    <div class="page-tabs" role="tablist">${NATION_TABS.map(([k, label]) =>
      `<button type="button" role="tab" data-ntab="${k}" aria-selected="${k === tab}">${label}</button>`).join("")}</div>
    <div id="nat-tab"></div>`;
  renderNationTab();
}

function renderNationTab() {
  const tab = state.nationTab || "overview";
  document.querySelectorAll("#club-body [data-ntab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.ntab === tab)));
  $("#nat-tab").innerHTML = tab === "overview" ? nationOverviewTab()
    : state.nation.team === undefined ? `<div class="empty-state">Loading ${escapeHtml(state.nation.name)}'s matches…</div>`
    : !state.nation.team?.matchRows.length ? `<div class="empty-state">No line-ups for ${escapeHtml(state.nation.name)} yet (they come from API-Football's international matches).</div>`
    : tab === "xi" ? nationXiTab() : tab === "formations" ? nationFormationsTab() : nationPlayersTab();
}

// ---- Overview: the top 3 in each position, where they play, and every ranked player
function nationOverviewTab() {
  const { name, list, allPlayers } = state.nation;
  if (!list.length) return `<div class="empty-state">No ranked players from ${escapeHtml(name)}.</div>`;
  // The pitch: the best by current rank in each position of the team's usual shape (3 per player the
  // shape has there: 6 for a pair of centre-backs), each player in the nearest of its positions to
  // his main one. Without line-ups, the top 3 in each of a fixed set of positions. Keeper at the
  // top, attacking down the page (so the left-sided positions are on the right), as the club pitches
  const shape = state.nation.team?.matchRows.length ? nationShape() : null;
  const layout = shape
    ? [...shape.need].sort((a, b) => ROLE_ORDER.indexOf(a[0]) - ROLE_ORDER.indexOf(b[0]))
      .map(([role, n]) => [role, 3 * n, ...ROLE_CELL[role]])
    : [["GK", 3, 1, 2], ["RB", 3, 2, 1], ["CB", 3, 2, 2], ["LB", 3, 2, 3], ["DM", 3, 3, 2], ["CM", 3, 4, 2],
       ["RW", 3, 5, 1], ["AM", 3, 5, 2], ["LW", 3, 5, 3], ["ST", 3, 6, 2]];
  const roles = new Set(layout.map((l) => l[0]));
  const slotOf = (pos) => (POS_FIT[pos] || [pos]).find((r) => roles.has(r));
  // With line-ups, everyone the current coach has picked (played for him, starting or from the bench)
  // is added to his position too: our ranked players by their main position, the rest by the one
  // they've started in most for him. Top players he hasn't picked are shown in red
  const picked = new Map();                          // player -> {id, name, rank, position} (rank null: not ranked)
  if (shape) {
    const inSpell = new Set(shape.spell.rows.map((m) => m.i));
    const started = new Map();
    for (const a of state.nation.team.appRows) {
      if (!inSpell.has(a.match)) continue;
      if (!picked.has(a.player)) picked.set(a.player, null);
      if (a.started && a.role) {
        const c = started.get(a.player) || new Map();
        started.set(a.player, c.set(a.role, (c.get(a.role) || 0) + 1));
      }
    }
    for (const pid of picked.keys()) {
      const p = list.find((q) => q.id === pid);
      const role = [...(started.get(pid) || [])].sort((a, b) => b[1] - a[1])[0]?.[0];
      picked.set(pid, p ? { id: pid, name: p.name, rank: p.rank, position: p.position, team: p.team }
        : { id: pid, name: state.nation.team.players[pid] || "Unknown", rank: null, position: role });
    }
  }
  const coach = shape?.spell.coach;
  const pitchRow = (p, unpicked) => {
    const tip = `${p.name}${p.team ? ` · ${teamName(p.team)}` : ""}${unpicked ? ` · not picked by ${coach || "the current coach"}` : ""}`;
    const inner = `<span class="dp-name">${escapeHtml(shortName(p.name))}</span><span class="dp-rank${p.rank == null ? "" : ` t${rankTier(p.rank)}`}">${p.rank == null ? "–" : Math.round(p.rank)}</span>`;
    const cls = `dp-row nat-row${unpicked ? " nat-unpicked" : ""}`;
    return playerById(p.id) ? `<a class="${cls}" href="#/player/${p.id}" title="${escapeHtml(tip)}">${inner}</a>`
      : `<span class="${cls}" title="${escapeHtml(tip)}">${inner}</span>`;
  };
  const spots = layout.map(([label, max, row, col]) => {
    const top = list.filter((p) => slotOf(p.position) === label).slice(0, max);
    const topIds = new Set(top.map((p) => p.id));
    const extra = [...picked.values()].filter((p) => p.position && slotOf(p.position) === label && !topIds.has(p.id));
    const ps = [...top.map((p) => [p, shape != null && !picked.has(p.id)]), ...extra.map((p) => [p, false])]
      .sort((a, b) => (b[0].rank ?? -1) - (a[0].rank ?? -1));
    const cell = `grid-row:${row};grid-column:${col}`;
    if (!ps.length) return `<div class="dp-spot empty" style="${cell}"><span class="dp-pos">${label}</span></div>`;
    return `<div class="dp-spot" style="${cell}"><span class="dp-pos">${label}</span>${ps.map(([p, unpicked]) => pitchRow(p, unpicked)).join("")}</div>`;
  }).join("");
  const LIMIT = 100;
  const row = (p, i) => `<div class="team-row"><span class="team-row-date">${i + 1}. ${escapeHtml(p.position || "")}</span>
    <span class="team-row-opp">${playerLink(p.id, p.name)} <span class="club-sub" style="display:inline">${playerClub(p)}${p.age != null ? ` · ${p.age}` : ""}</span></span>
    <span class="team-row-res">${rankChipSmall(p.rank)}</span></div>`;
  const shown = allPlayers ? list : list.slice(0, LIMIT);
  return `
    <div class="club-section"><div class="modal-section">${shape ? `Best by current rank in their usual ${escapeHtml(shape.formation)}` : "Top 3 in each position by current rank"}</div>
      <div class="pp-section"><div class="pitch dp-pitch">${PITCH_LINES}${spots}</div>
        ${shape ? `<div class="page-note" style="text-align:center">Plus everyone ${escapeHtml(coach || "the current coach")} has picked. <span class="nat-unpicked-key">Red</span>: not picked by him.</div>` : ""}</div></div>
    <div class="club-section"><div class="modal-section">All players</div><div>${shown.map(row).join("")}</div>
      ${shown.length < list.length ? `<button type="button" class="show-all" data-nat-more>Show all ${list.length.toLocaleString()}</button>` : ""}</div>`;
}

// The current coach's matches (oldest first). With his start date (team_coaches, when he's the coach
// on the latest team sheet): the matches since then. Else his unbroken spell up to the latest match
// on the team sheets, from his first known one. Every match when the latest names no coach.
// full: the stored matches go back to the start of his spell
function nationSpell() {
  const { matchRows: rows, coach: head } = state.nation.team;
  const last = rows[rows.length - 1];
  if (head?.since && head.name && (last.coach_id == null || last.coach_id === head.id)) {
    const list = rows.filter((m) => m.date >= head.since);
    if (list.length) return { coach: head.name, coachId: head.id, since: head.since, rows: list,
      full: rows[0].date <= head.since };
  }
  const coach = last.coach;
  if (!coach) return { coach: null, rows, full: false };
  let k = rows.length;
  while (k > 0 && (rows[k - 1].coach === coach || rows[k - 1].coach == null)) k--;
  while (rows[k].coach == null) k++;
  return { coach, coachId: last.coach_id, rows: rows.slice(k), full: k > 0 };
}
const spellLabel = ({ coach }) => coach ? `Under ${coach}` : "All matches (coach not known)";

// Opponent (flag and name, linking to its page), venue and result of a national team match
const venueLabel = { H: "Home", A: "Away", N: "Neutral ground" };
function nationMatchCells(m) {
  return `<span class="team-row-date">${escapeHtml(fmtDateShortYear(m.date))}</span>
    <span class="team-row-opp">${flagImg(m.opp)} <a class="nat-link" href="#/nation/${encodeURIComponent(m.opp)}">${escapeHtml(m.opp)}</a>
      <span class="club-sub" style="display:inline" title="${escapeHtml(venueLabel[m.venue] || "")}">${escapeHtml(m.venue)} · ${escapeHtml(m.tournament || "")}</span></span>
    <span class="rel-chip rel-${m.gf > m.ga ? 4 : m.gf === m.ga ? 3 : 1}">${m.gf}–${m.ga}</span>`;
}
// A starting XI as one line per unit, keeper first: "GK Pickford · RB Walker ..."
const ROLE_ORDER = ["GK", "RB", "RWB", "CB", "LB", "LWB", "DM", "RM", "CM", "LM", "AM", "RW", "ST", "LW"];
// Each role's cell on the overview pitch [row, column] (column 1 is the right: attacking down the page)
const ROLE_CELL = { GK: [1, 2], RB: [2, 1], CB: [2, 2], LB: [2, 3], RWB: [3, 1], DM: [3, 2], LWB: [3, 3],
  RM: [4, 1], CM: [4, 2], LM: [4, 3], RW: [5, 1], AM: [5, 2], LW: [5, 3], ST: [6, 2] };
// A player's main position -> the roles he fits, nearest first (the first the shape has is his)
const POS_FIT = { GK: ["GK"], CB: ["CB", "DM"], RB: ["RB", "RWB", "RM", "CB"], LB: ["LB", "LWB", "LM", "CB"],
  RWB: ["RWB", "RB", "RM", "RW"], LWB: ["LWB", "LB", "LM", "LW"], DM: ["DM", "CM", "CB"], CM: ["CM", "DM", "AM"],
  AM: ["AM", "CM", "ST", "RW", "LW"], RM: ["RM", "RW", "RWB", "AM", "CM"], LM: ["LM", "LW", "LWB", "AM", "CM"],
  RW: ["RW", "RM", "AM", "ST"], LW: ["LW", "LM", "AM", "ST"], ST: ["ST", "AM"] };
function nationXi(m) {
  const names = state.nation.team.players;
  const xi = m.xi.slice().sort((a, b) => (ROLE_ORDER.indexOf(a.role) + 1 || 99) - (ROLE_ORDER.indexOf(b.role) + 1 || 99));
  if (!xi.length) return `<div class="page-note">No starting XI for this match.</div>`;
  return `<div class="nat-xi">${xi.map((a) => {
    const name = names[a.player] || "Unknown";
    return `<span><span class="nat-xi-role">${escapeHtml(a.role || "–")}</span>${playerById(a.player) ? playerLink(a.player, shortName(name)) : escapeHtml(shortName(name))}${
      a.goals ? ` <span class="nat-xi-goals" title="${a.goals} goal${a.goals === 1 ? "" : "s"}">${"⚽".repeat(Math.min(a.goals, 4))}</span>` : ""}</span>`;
  }).join("")}</div>`;
}

// ---- Predicted XI: from the current coach's recent team sheets (no model). His most used formation
// in his last 5 matches, laid out as his latest XI in it; then each of its positions goes to the
// player who has started there most, recent matches counting more (a start in a neighbouring
// position counts half). Players their club lists as out injured are left out.
const NAT_XI_RECENT = 6;        // his latest team sheets weighed
const NAT_XI_DECAY = 0.75;      // each older sheet counts this much of the one after it
const ROLE_NEAR = { GK: [], CB: [], RB: ["RWB"], LB: ["LWB"], RWB: ["RB", "RM"], LWB: ["LB", "LM"], DM: ["CM"],
  CM: ["DM", "AM"], AM: ["CM", "ST"], RM: ["RW", "RWB"], LM: ["LW", "LWB"], RW: ["RM", "ST"], LW: ["LM", "ST"], ST: ["AM"] };
// players their club's latest injury list has missing through injury (the list's "injured" flag)
function injuredPlayers() {
  const out = new Set(), fields = state.injuries?.fields || [];
  const [pi, ii] = ["player", "injured"].map((f) => fields.indexOf(f));
  for (const t of Object.values(state.injuries?.teams || {}))
    for (const r of t.players || []) if (r[ii]) out.add(r[pi]);
  return out;
}
// The team's usual shape: its most used formation in the current coach's last 5 team sheets (ties:
// the latest), as {role: count} from his latest XI in it. Null without full team sheets
function nationShape() {
  const spell = nationSpell();
  const sheets = spell.rows.filter((m) => m.xi.length >= 11 && m.xi.every((a) => a.role)).slice(-NAT_XI_RECENT);
  if (!sheets.length) return null;
  const counts = new Map();
  for (const m of sheets.slice(-5)) if (m.formation) counts.set(m.formation, (counts.get(m.formation) || 0) + 1);
  const latest = [...sheets].reverse();
  const formation = [...counts].sort((a, b) => b[1] - a[1]
    || latest.findIndex((m) => m.formation === a[0]) - latest.findIndex((m) => m.formation === b[0]))[0]?.[0];
  const template = latest.find((m) => m.formation === formation) || latest[0];
  const need = new Map();
  for (const a of template.xi) need.set(a.role, (need.get(a.role) || 0) + 1);
  return { spell, sheets, formation: template.formation, template, need };
}
function nationPredictedXi() {
  const shape = nationShape();
  if (!shape) return null;
  const { spell, sheets, template, need } = shape;
  const injured = injuredPlayers();
  const score = new Map(), starts = new Map();
  sheets.forEach((m, k) => {
    const w = NAT_XI_DECAY ** (sheets.length - 1 - k);
    for (const a of m.xi) {
      starts.set(a.player, (starts.get(a.player) || 0) + 1);
      for (const [role, f] of [[a.role, 1], ...(ROLE_NEAR[a.role] || []).map((r) => [r, 0.5])])
        score.set(`${role}:${a.player}`, (score.get(`${role}:${a.player}`) || 0) + f * w);
    }
  });
  const picks = [], placed = new Set(), filled = new Map();
  [...score].map(([key, v]) => { const [role, pid] = key.split(":"); return { role, pid: Number(pid), v }; })
    .filter((c) => need.has(c.role) && !injured.has(c.pid))
    .sort((a, b) => b.v - a.v || (starts.get(b.pid) || 0) - (starts.get(a.pid) || 0))
    .forEach((c) => {
      if (placed.has(c.pid) || (filled.get(c.role) || 0) >= need.get(c.role)) return;
      placed.add(c.pid);
      filled.set(c.role, (filled.get(c.role) || 0) + 1);
      picks.push({ ...c, starts: starts.get(c.pid) || 0 });
    });
  // regulars (2+ starts in these sheets) missing through injury
  const out = [...starts].filter(([pid, n]) => n >= 2 && injured.has(pid)).map(([pid]) => ({ pid }));
  return { formation: template.formation, sheets, template, picks, out, spell };
}
function nationXiTab() {
  const pred = nationPredictedXi();
  if (!pred) return `<div class="empty-state">Not enough line-ups to predict ${escapeHtml(state.nation.name)}'s XI yet.</div>`;
  const { players: names } = state.nation.team;
  const name = (pid) => names[pid] || playerById(pid)?.name || "Unknown";
  const order = (r) => ROLE_ORDER.indexOf(r) + 1 || 99;
  const picks = pred.picks.slice().sort((a, b) => order(a.role) - order(b.role));
  const xi = picks.map((c) => ({ b: { label: c.role }, p: { id: c.pid, name: name(c.pid) }, rank: playerById(c.pid)?.rank ?? null }));
  const who = (pid) => `${personChip(name(pid))}${
    playerById(pid) ? playerLink(pid, shortName(name(pid))) : `<span title="${escapeHtml(name(pid))}">${escapeHtml(shortName(name(pid)))}</span>`}`;
  const side = `
    ${pred.out.length ? `<div class="next-card"><div class="next-top"><span class="next-label">Out injured</span></div>
      ${pred.out.map((o) => `<div class="nat-xi-row"><span class="nat-xi-who">${who(o.pid)}</span></div>`).join("")}</div>` : ""}`;
  const pitch = xiPitch(xi, {}, { note: "" });
  return side.trim() ? `<div class="ov-top"><div class="ov-side">${side}</div>${pitch}</div>` : pitch;
}

// ---- Formations: the current coach, the formations used under him, then match by match with each
// starting XI (click a match to open it)
function nationFormationsTab() {
  const spell = nationSpell();
  const list = spell.rows;
  const known = list.filter((m) => m.formation);
  return `
    ${spell.coach ? `<div class="next-card coach-card">${personChip(spell.coach, "coach-photo")}
      <div><div class="next-label">Head coach</div><div class="coach-name">${escapeHtml(spell.coach)}</div>
      <div class="next-meta"><span>${spell.since ? `Since ${escapeHtml(fmtLongDate(spell.since))}` : `First match ${escapeHtml(fmtLongDate(list[0].date))}${spell.full ? "" : " (or before)"}`}</span><span>${list.length} matches${
        spell.since && !spell.full ? ` from ${escapeHtml(fmtLongDate(list[0].date))}` : ""} · ${wdl(list)}</span></div></div></div>` : ""}
    <div class="club-section"><div class="modal-section">Formations · ${escapeHtml(spellLabel(spell))}</div>
      ${known.length ? formationCards(known) : `<div class="page-note">No formations known for these matches.</div>`}
      ${known.length < list.length ? `<div class="page-note">${list.length - known.length} match${list.length - known.length === 1 ? "" : "es"} with no known line-up not counted.</div>` : ""}</div>
    <div class="club-section"><div class="modal-section">Match by match</div>
      ${list.slice().reverse().map((m) => `<details class="nat-match"><summary class="team-row">${nationMatchCells(m)}
        <span class="nat-fm">${m.formation ? escapeHtml(m.formation) : "–"}</span></summary>${nationXi(m)}</details>`).join("")}</div>
    <div class="page-note">International matches API-Football has line-ups for${spell.full ? "" : `, from ${escapeHtml(fmtLongDate(list[0].date))}${spell.since ? "" : " (his spell may have started earlier)"}`}. Formations as on each team sheet.</div>`;
}

// ---- Players: everyone who has played under the current coach, with appearances, starts, minutes,
// goals, assists, average match rating and cards
const NAT_PLAYER_COLS = [
  ["apps", "Apps", "Matches played, starting or from the bench."],
  ["minutes", "Mins", "Minutes played (where API-Football has the player's stat line)."], ["goals", "G", "Goals."],
  ["assists", "A", "Assists."], ["rating", "Rating", "Average API-Football match rating (matches with one)."],
  ["cards", "Cards", "Yellow and red cards."], ["last", "Last", "Date of his latest appearance."],
];
function nationPlayersTab() {
  const { team } = state.nation;
  const spell = nationSpell();
  const list = spell.rows;
  const inWindow = new Set(list.map((m) => m.i));
  const by = new Map();
  for (const a of team.appRows) {
    if (!inWindow.has(a.match)) continue;
    let p = by.get(a.player);
    if (!p) by.set(a.player, p = { id: a.player, name: team.players[a.player] || "Unknown", apps: 0, minutes: 0,
      noMins: 0, goals: 0, assists: 0, ratings: [], y: 0, r: 0, last: "", roles: new Map() });
    const m = team.matchRows[a.match];
    p.apps++;
    if (a.minutes == null) p.noMins++; else p.minutes += a.minutes;
    p.goals += a.goals || 0; p.assists += a.assists || 0;
    if (a.rating != null) p.ratings.push(a.rating);
    p.y += a.yellow || 0; p.r += a.red || 0;
    if (m.date > p.last) p.last = m.date;
    if (a.role) p.roles.set(a.role, (p.roles.get(a.role) || 0) + 1);
  }
  const players = [...by.values()];
  for (const p of players) {
    p.rating = p.ratings.length ? p.ratings.reduce((x, y) => x + y, 0) / p.ratings.length : null;
    p.cards = p.y + 3 * p.r;
    p.role = [...p.roles].sort((a, b) => b[1] - a[1])[0]?.[0] || playerById(p.id)?.position || "";
  }
  const key = state.nationPlayerSort || "minutes";
  const val = (p) => key === "last" ? p.last : p[key] ?? -Infinity;
  players.sort((a, b) => (val(b) > val(a) ? 1 : val(b) < val(a) ? -1 : 0) || b.apps - a.apps || b.minutes - a.minutes);
  const th = ([k, label, tip]) => `<th class="num sortable${key === k ? " active" : ""}" tabindex="0"${key === k ? ` aria-sort="descending"` : ""} data-natpsort="${k}" title="${escapeHtml(tip + " Click to sort.")}">${label}</th>`;
  const anyNoMins = players.some((p) => p.noMins);
  return `<div class="modal-section nat-spell">${escapeHtml(spellLabel(spell))}${spell.since ? ` (since ${escapeHtml(fmtLongDate(spell.since))})` : ""} · ${list.length} match${list.length === 1 ? "" : "es"}${
    spell.full ? "" : ` from ${escapeHtml(fmtLongDate(list[0].date))}`}</div>
    <div class="table-scroll"><table class="leaderboard nat-players">
      <thead><tr><th>#</th><th>Player</th><th title="His most common starting role in these matches (else his club position).">Pos</th>${NAT_PLAYER_COLS.map(th).join("")}</tr></thead>
      <tbody>${players.map((p, i) => {
        const site = playerById(p.id);
        return `<tr>
          <td>${i + 1}</td>
          <td><div class="club-cell">${personChip(p.name)}${site ? playerLink(p.id, shortName(p.name)) : `<span title="${escapeHtml(p.name)}">${escapeHtml(shortName(p.name))}</span>`}${
            site?.team ? `<a class="pl-badge-link nat-badge" href="${clubHref(site.team)}" title="${escapeHtml(teamName(site.team))}" aria-label="${escapeHtml(teamName(site.team))}">${clubCrest(site.team, "club-logo")}</a>` : ""}</div></td>
          <td>${escapeHtml(p.role)}</td>
          <td class="num">${p.apps}</td>
          <td class="num"${p.noMins ? ` title="Minutes not known for ${p.noMins} of his matches"` : ""}>${p.noMins === p.apps ? "–" : `${p.minutes}${p.noMins ? "*" : ""}`}</td>
          <td class="num">${p.goals || ""}</td><td class="num">${p.assists || ""}</td>
          <td class="num">${p.rating != null ? p.rating.toFixed(2) : "–"}</td>
          <td class="num">${p.y ? `<span class="card-y" title="Yellow cards">${p.y}</span>` : ""}${p.r ? `<span class="card-r" title="Red cards">${p.r}</span>` : ""}</td>
          <td class="num">${escapeHtml(fmtDateShortYear(p.last))}</td></tr>`;
      }).join("")}</tbody></table></div>
    <div class="page-note">${players.length} players in ${list.length} matches, from API-Football's line-ups and player stats. Click a heading to sort.${
      anyNoMins ? " * Includes starts with no stat line, whose minutes aren't known." : ""}</div>`;
}

$("#club-body").addEventListener("click", (e) => {
  if (!state.nation) return;
  const t = e.target.closest("[data-ntab]");
  const th = e.target.closest("th[data-natpsort]");
  if (t) state.nationTab = t.dataset.ntab;
  else if (th) state.nationPlayerSort = th.dataset.natpsort;
  else if (e.target.closest("[data-nat-more]")) state.nation.allPlayers = true;
  else return;
  renderNationTab();
});

// ------------------------------------------------------------------ league and country pages
const leagueCache = new Map();
// A league's file (cached), for league pages and the domestic position on club pages
async function loadLeague(lid) {
  if (leagueCache.has(lid)) return leagueCache.get(lid);
  const lg = await getJsonOrNull(`data/leagues/${lid}.json`);
  if (lg) {
    lg.tableRows = rowsToObjects(lg.table_fields, lg.table);
    // each club's xG and xG conceded per 90 over its last five league games with xG (older files: none)
    const xf = lg.recent_xg_fields || [];
    for (const r of lg.tableRows) {
      const x = lg.recent_xg?.[r.team];
      r.xg90 = x ? x[xf.indexOf("xg90")] : null; r.xga90 = x ? x[xf.indexOf("xga90")] : null; r.xg_games = x ? x[xf.indexOf("games")] : 0;
    }
    lg.fixtureRows = rowsToObjects(lg.fixture_fields, lg.fixtures);
    leagueCache.set(lid, lg);
  }
  return lg;
}
// Actual standings, TheCornerFC's strength ranking and the projected table are kept on separate
// tabs, each saying which it is: a club's league position and its model ranking are different things
const LEAGUE_TABS = [["table", "Standings"], ["clubs", "Strength ranking"], ["projected", "Projected table"], ["matches", "Matches"]];
const roundLabel = (r) => (r || "").replace(/^Regular Season - (\d+)$/, "Round $1");
const OFF = new Set(["CANC", "PST", "ABD"]);
// clubs playing their league football in this competition this season, best rated first
const leagueClubs = (lid) => state.rankings.filter((r) => r.in_league && r.league === lid).sort((a, b) => b.lt - a.lt);
const avgRating = (rows) => rows.length ? rows.reduce((a, r) => a + r.lt, 0) / rows.length : null;
// a rating's place among every ranked club, as the badge colours (top 5% green ...)
function ratingTierOf(v) {
  const share = (state.rankings.filter((x) => x.lt > v).length + 1) / state.rankings.length;
  return share <= 0.05 ? 4 : share <= 0.2 ? 3 : share <= 0.5 ? 2 : 1;
}
// "2026/27" for a season that starts in the second half of the year, "2026" for a calendar-year
// one (API-Football's end dates only reach the last fixture it has scheduled)
function seasonLabel(lg) {
  const month = Number((lg.start || lg.fixtures[0]?.[1] || "").slice(5, 7));
  return month >= 6 ? `${lg.season}/${String(lg.season + 1).slice(2)}` : String(lg.season);
}

async function openLeaguePage(lid, want = null) {
  showPage(compLabel(lid));
  state.club = null;
  const comp = state.data.competitions[lid];
  $("#club-body").innerHTML = `<div class="empty-state">Loading ${escapeHtml(comp?.name || "competition")}…</div>`;
  const lg = await loadLeague(lid);
  if (Number(location.hash.match(/^#\/league\/(\d+)/)?.[1]) !== lid) return;      // moved on while loading
  const tabs = LEAGUE_TABS.filter(([k]) => (k !== "table" && k !== "projected") || lg?.tableRows.length);
  const has = (k) => tabs.some(([t]) => t === k);
  const keep = state.league?.id === lid && has(state.league.tab);
  // the tab in the link (#/league/39/clubs), else the one open before, else the standings (a cup
  // without a table: its matches)
  const tab = has(want) ? want : keep ? state.league.tab : has("table") ? "table" : "matches";
  state.league = { id: lid, data: lg, tabs, tab, round: keep ? state.league.round : null };
  renderLeaguePage();
}

function renderLeaguePage() {
  const { id, data } = state.league;
  const comp = state.data.competitions[id] || { name: compLabel(id), country: "World", type: "" };
  const avg = avgRating(leagueClubs(id));
  $("#club-body").innerHTML = `
    <div class="pl-hero">
      ${leagueCrest(id, "club-logo-lg")}
      <div class="pl-hero-main">
        <h2>${escapeHtml(comp.name)}</h2>
        <div class="pl-hero-club">${flagImg(countryDisplay(comp.country))}<span>${countryLink(comp.country)}</span></div>
      </div>
      ${avg != null ? `<div class="pl-hero-rank rel-${ratingTierOf(avg)}" title="Average Baseline Strength (long-term Elo) of the clubs playing in this league">
        <span class="val">${Math.round(avg)}</span></div>` : ""}
    </div>
    ${data ? `<div class="page-tabs" role="tablist">${state.league.tabs.map(([k, label]) =>
      `<button type="button" role="tab" data-ltab="${k}" aria-selected="${k === state.league.tab}">${label}</button>`).join("")}</div>
    <div id="league-tab"></div>` : loadFailed(`leagues/${state.league.id}`) ? loadError("this competition") : `<div class="empty-state">No data for this competition this season.</div>`}`;
  if (data) renderLeagueTab();
}

// The clubs in a competition that have a rating: this season's league members plus anyone in its
// table (or, with no table yet, its fixtures), strongest first by Baseline Strength
function leagueRanked(id, data) {
  const ids = new Set([...data.tableRows.map((r) => r.team), ...leagueClubs(id).map((r) => r.team)]);
  if (!data.tableRows.length) data.fixtureRows.forEach((f) => { ids.add(f.home); ids.add(f.away); });
  return [...ids].map((t) => state.rankByTeam.get(t)).filter(Boolean).sort((a, b) => b.lt - a.lt);
}

function renderLeagueTab() {
  const tab = state.league.tab;
  document.querySelectorAll("#club-body [data-ltab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.ltab === tab)));
  $("#league-tab").innerHTML = tab === "table" ? leagueTableTab() : tab === "projected" ? leagueProjectedTab()
    : tab === "matches" ? leagueMatchesTab() : leagueClubsTab();
}

// ---- Standings: this season's actual table, one table per group, zones coloured from API-Football's notes
const ZONE_COLOURS = ["var(--series-blue)", "var(--series-aqua)", "var(--status-good)", "var(--status-warning)", "var(--text-muted)"];
function leagueZones(rows) {
  const zones = new Map();
  let next = 0, releg = 0;
  for (const r of rows) {
    if (!r.description || zones.has(r.description)) continue;
    zones.set(r.description, /relegation/i.test(r.description)
      ? (releg++ ? "var(--series-orange)" : "var(--status-critical)") : ZONE_COLOURS[Math.min(next++, ZONE_COLOURS.length - 1)]);
  }
  return zones;
}
// API-Football's form string (newest first, as the club page's results) as W/D/L chips
const formChips = (f) => f ? `<span class="lt-form">${[...f].map((c) =>
  `<i class="${c === "W" ? "res-w" : c === "D" ? "res-d" : "res-l"}">${escapeHtml(c)}</i>`).join("")}</span>` : "";
const zoneLegend = (zones) => zones.size ? `<div class="lt-legend">${[...zones].map(([d, c]) =>
  `<span><i style="background:${c}"></i>${escapeHtml(d)}</span>`).join("")}</div>` : "";
// Sortable league tables (Standings, Strength ranking): the viewer's column per tab, kept on
// state.league. A column's first click sorts it best first (1 = asc, -1 = desc), a second reverses.
// Ties keep the table's own order.
function leagueSort(tab, cols, def) {
  const s = (state.league.sort ||= {})[tab] ||= { key: def, dir: cols[def].dir };
  return s;
}
function sortLeagueRows(rows, s, cols) {
  const val = cols[s.key].val;
  return rows.map((r, i) => [r, i]).sort(([a, i], [b, j]) => {
    const x = val(a), y = val(b);
    if (x == null || y == null) return x == null && y == null ? i - j : x == null ? 1 : -1;   // blanks last
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * s.dir || i - j;
  }).map(([r]) => r);
}
// a sortable header cell: tab and key go in data-lsort; the active one is marked and shows its direction
function sortTh(tab, s, key, label, title, cls = "") {
  const on = s.key === key;
  return `<th class="${cls}${cls ? " " : ""}sortable${on ? " active" : ""}" tabindex="0" data-lsort="${tab}:${key}" title="${escapeHtml(title + ". Click to sort.")}"${on ? ` aria-sort="${s.dir > 0 ? "ascending" : "descending"}"` : ""}>${label}${on ? `<span class="sort-dir">${s.dir > 0 ? "▲" : "▼"}</span>` : ""}</th>`;
}
const FORM_PTS = { W: 3, D: 1, L: 0 };
const STANDINGS_COLS = {
  rank: { dir: 1, val: (r) => r.rank }, club: { dir: 1, val: (r) => r.name },
  played: { dir: -1, val: (r) => r.played }, win: { dir: -1, val: (r) => r.win }, draw: { dir: -1, val: (r) => r.draw },
  lose: { dir: -1, val: (r) => r.lose }, gf: { dir: -1, val: (r) => r.gf }, ga: { dir: 1, val: (r) => r.ga },
  gd: { dir: -1, val: (r) => r.gd }, points: { dir: -1, val: (r) => r.points },
  xg90: { dir: -1, val: (r) => r.xg90 }, xga90: { dir: 1, val: (r) => r.xga90 },
  form: { dir: -1, val: (r) => r.form ? [...r.form].reduce((a, c) => a + (FORM_PTS[c] ?? 0), 0) : null },
  current: { dir: -1, val: (r) => state.rankByTeam.get(r.team)?.current },
};
function leagueTableTab() {
  const { data } = state.league;
  const rows = data.tableRows.map((r) => ({ ...r, name: data.teams[r.team] || teamName(r.team) }));
  const s = leagueSort("table", STANDINGS_COLS, "rank");
  const th = (key, label, title, cls) => sortTh("table", s, key, label, title, cls);
  const hasXg = rows.some((r) => r.xg90 != null);   // leagues without xG data don't get the columns
  if (!hasXg && s.key.startsWith("xg")) Object.assign(s, { key: "rank", dir: 1 });
  const xgTip = (r) => r.xg_games ? ` title="Over the last ${r.xg_games} league game${r.xg_games === 1 ? "" : "s"} with xG"` : "";
  const zones = leagueZones(rows);
  const groups = [...new Set(rows.map((r) => r.group))];
  const table = (g) => `
    ${groups.length > 1 ? `<div class="modal-section">${escapeHtml(g)}</div>` : ""}
    <div class="table-scroll"><table class="league-table">
      <thead><tr>${th("rank", "#", "Position", "lt-pos")}<th></th>${th("club", "Club", "Club name", "lt-club")}
        ${th("played", "P", "Played")}${th("win", "W", "Won", "lt-wdl")}${th("draw", "D", "Drawn", "lt-wdl")}${th("lose", "L", "Lost", "lt-wdl")}
        ${th("gf", "GF", "Goals for", "lt-wide")}${th("ga", "GA", "Goals against", "lt-wide")}${th("gd", "GD", "Goal difference", "lt-gd")}${th("points", "Pts", "Points")}
        ${hasXg ? th("xg90", "xG/90", "Expected goals per 90 minutes over the club's last five league games") + th("xga90", "xGC/90", "Expected goals conceded per 90 minutes over the club's last five league games") : ""}
        ${th("form", "Form", "Last five league games, newest first: green won, grey drawn, red lost. Sorts by points from them", "lt-formcol")}${th("current", "Current", "Current Strength: the club's current Elo rating")}</tr></thead>
      <tbody>${sortLeagueRows(rows.filter((r) => r.group === g), s, STANDINGS_COLS).map((r) => {
        const rk = state.rankByTeam.get(r.team);
        return `<tr><td class="lt-pos" style="border-left-color:${zones.get(r.description) || "transparent"}">${r.rank}</td>
          <td class="lt-badge">${clubCrest(r.team, "club-logo", `data-club="${r.team}"`)}</td>
          <td class="lt-club">${clubLink(r.team, r.name)}</td>
          <td>${r.played ?? ""}</td><td class="lt-wdl">${r.win ?? ""}</td><td class="lt-wdl">${r.draw ?? ""}</td><td class="lt-wdl">${r.lose ?? ""}</td>
          <td class="lt-wide">${r.gf ?? ""}</td><td class="lt-wide">${r.ga ?? ""}</td><td class="lt-gd">${r.gd > 0 ? "+" : ""}${r.gd ?? ""}</td><td><b>${r.points ?? ""}</b></td>
          ${hasXg ? `<td${xgTip(r)}>${r.xg90 != null ? r.xg90.toFixed(2) : ""}</td><td${xgTip(r)}>${r.xga90 != null ? r.xga90.toFixed(2) : ""}</td>` : ""}
          <td class="lt-formcol">${formChips(r.form)}</td><td class="lt-elo">${rk ? Math.round(rk.current) : ""}</td></tr>`;
      }).join("")}</tbody></table></div>`;
  return groups.map(table).join("") + zoneLegend(zones);
}

// ---- Projected: the rest of the season played out SIMS times from the model's predictions. Each
// upcoming match's score is drawn from its Poisson grid, scaled to its home / draw / away chances.
// Each simulated season also gives every club a random true strength (STRENGTH_SD, on the log of its
// expected goals), shared by all its matches: the model's ratings are estimates, and a club that is
// really a little better or worse is so every week. Without it the matches are independent coin
// flips, their luck evens out over a season and the leaders' chances come out far too high.
const SIMS = 5000;
const STRENGTH_SD = 0.15;
const SHIFT_STEP = 0.05, SHIFT_MAX = 16;  // strength gaps rounded to 0.05, capped at ±0.8
const pmf = (lam) => { const out = [], m = Math.max(lam, 0.01); let p = Math.exp(-m);
  for (let k = 0; k <= 10; k++) { out.push(p); p *= m / (k + 1); } return out; };
// one match's scores at a strength gap of `shift` (home minus away), most likely first, as cumulative
// chances (hg, ag in 0-10). The model's result chances are kept by reweighting each result by the
// same factor that matches the unshifted grid to them.
function scoreTable(f, shift = 0) {
  if (!f.fix) {
    const ph = pmf(f.home_xg), pa = pmf(f.away_xg), sums = [0, 0, 0];   // home win, draw, away win
    for (let i = 0; i <= 10; i++) for (let j = 0; j <= 10; j++) sums[i > j ? 0 : i === j ? 1 : 2] += ph[i] * pa[j];
    f.fix = [f.p_home, f.p_draw, f.p_away].map((w, k) => sums[k] ? w / sums[k] : 0);
  }
  const e = Math.exp(shift), ph = pmf(f.home_xg * e), pa = pmf(f.away_xg / e);
  const cells = [];
  for (let i = 0; i <= 10; i++) for (let j = 0; j <= 10; j++)
    cells.push({ i, j, p: ph[i] * pa[j] * f.fix[i > j ? 0 : i === j ? 1 : 2] });
  cells.sort((x, y) => y.p - x.p);
  const cdf = new Float64Array(cells.length), hg = new Int8Array(cells.length), ag = new Int8Array(cells.length);
  let acc = 0;
  cells.forEach((c, n) => { cdf[n] = acc += c.p; hg[n] = c.i; ag[n] = c.j; });
  return { cdf, hg, ag, total: acc };
}
const gauss = () => Math.sqrt(-2 * Math.log(1 - Math.random())) * Math.cos(2 * Math.PI * Math.random());
function projectGroup(rows, fixtures) {
  const n = rows.length, idx = new Map(rows.map((r, i) => [r.team, i]));
  const games = fixtures.filter((f) => idx.has(f.home) || idx.has(f.away)).map((f) => {
    const g = { h: idx.has(f.home) ? idx.get(f.home) : -1, a: idx.has(f.away) ? idx.get(f.away) : -1, f,
      tables: new Array(2 * SHIFT_MAX + 1) };
    g.tables[SHIFT_MAX] = scoreTable(f);
    return g;
  });
  // clubs outside this group (other groups' opponents) get their own strength draw too
  const outside = new Map(); let m = n;
  for (const f of fixtures) for (const t of [f.home, f.away]) if (!idx.has(t) && !outside.has(t)) outside.set(t, m++);
  const slot = (g, side) => { const i = side === "h" ? g.h : g.a; return i >= 0 ? i : outside.get(side === "h" ? g.f.home : g.f.away); };
  games.forEach((g) => { g.hs = slot(g, "h"); g.as = slot(g, "a"); });
  const pos = rows.map(() => new Float64Array(n)), sumPts = new Float64Array(n), sumGd = new Float64Array(n);
  const pts = new Float64Array(n), gd = new Float64Array(n), gf = new Float64Array(n), tie = new Float64Array(n);
  const strength = new Float64Array(m);
  const order = rows.map((_, i) => i);
  for (let s = 0; s < SIMS; s++) {
    for (let i = 0; i < n; i++) { const r = rows[i]; pts[i] = r.points || 0; gd[i] = r.gd || 0; gf[i] = r.gf || 0; tie[i] = Math.random(); }
    for (let i = 0; i < m; i++) strength[i] = STRENGTH_SD * gauss();
    for (const g of games) {
      const k = Math.max(-SHIFT_MAX, Math.min(SHIFT_MAX, Math.round((strength[g.hs] - strength[g.as]) / SHIFT_STEP)));
      const t = g.tables[k + SHIFT_MAX] || (g.tables[k + SHIFT_MAX] = scoreTable(g.f, k * SHIFT_STEP));
      const u = Math.random() * t.total, cdf = t.cdf;
      let c = 0;
      while (c < cdf.length - 1 && cdf[c] < u) c++;
      const hg = t.hg[c], ag = t.ag[c], hp = hg > ag ? 3 : hg === ag ? 1 : 0, ap = hg < ag ? 3 : hg === ag ? 1 : 0;
      if (g.h >= 0) { pts[g.h] += hp; gd[g.h] += hg - ag; gf[g.h] += hg; }
      if (g.a >= 0) { pts[g.a] += ap; gd[g.a] += ag - hg; gf[g.a] += ag; }
    }
    order.sort((x, y) => pts[y] - pts[x] || gd[y] - gd[x] || gf[y] - gf[x] || tie[y] - tie[x]);
    for (let p = 0; p < n; p++) pos[order[p]][p]++;
    for (let i = 0; i < n; i++) { sumPts[i] += pts[i]; sumGd[i] += gd[i]; }
  }
  const left = rows.map(() => 0), xw = rows.map(() => 0), xd = rows.map(() => 0);
  for (const { h, a, f } of games) {
    if (h >= 0) { left[h]++; xw[h] += f.p_home; xd[h] += f.p_draw; }
    if (a >= 0) { left[a]++; xw[a] += f.p_away; xd[a] += f.p_draw; }
  }
  return rows.map((r, i) => ({ r, left: left[i], w: (r.win || 0) + xw[i], d: (r.draw || 0) + xd[i],
    l: (r.lose || 0) + left[i] - xw[i] - xd[i], pts: sumPts[i] / SIMS, gd: sumGd[i] / SIMS,
    pos: [...pos[i]].map((c) => c / SIMS) }))
    .sort((x, y) => y.pts - x.pts || y.gd - x.gd);
}
function leagueProjectedTab() {
  const { data } = state.league;
  const rows = data.tableRows;
  const upcoming = data.fixtureRows.filter((f) => f.p_home != null && f.home_xg != null);
  if (!upcoming.length) return `<div class="empty-state">No upcoming matches to project.</div>`;
  const groups = [...new Set(rows.map((r) => r.group))];
  if (!state.league.proj) {
    // worked out after the tab paints (it takes a moment), then drawn if still on this tab
    const lg = state.league;
    setTimeout(() => {
      lg.proj = new Map(groups.map((g) => [g, projectGroup(rows.filter((r) => r.group === g), upcoming)]));
      if (state.league === lg && lg.tab === "projected") renderLeagueTab();
    }, 30);
    return `<div class="empty-state">Playing out the rest of the season…</div>`;
  }
  const zones = leagueZones(rows);
  const pct = (p) => p <= 0 ? `<span class="dim">–</span>` : p < 0.005 ? "<1%" : p > 0.995 && p < 1 ? ">99%" : `${Math.round(p * 100)}%`;
  const table = (g) => {
    const list = state.league.proj.get(g);
    const byRank = new Map(rows.filter((r) => r.group === g).map((r) => [r.rank, r.description]));
    // a zone's chance: the chance of finishing in any of the places carrying its note today
    const cols = [...zones].filter(([d]) => [...byRank.values()].includes(d)).map(([d, c]) =>
      [d, c, [...byRank].filter(([, v]) => v === d).map(([k]) => k - 1)]);
    return `
    ${groups.length > 1 ? `<div class="modal-section">${escapeHtml(g)}</div>` : ""}
    <div class="table-scroll"><table class="league-table">
      <thead><tr><th class="lt-pos">#</th><th></th><th class="lt-club">Club</th>
        <th class="lt-wide" title="Matches left to play">Left</th><th class="lt-wdl" title="Projected wins">W</th><th class="lt-wdl" title="Projected draws">D</th><th class="lt-wdl" title="Projected losses">L</th>
        <th class="lt-gd" title="Projected goal difference">GD</th><th title="Projected points: points so far plus the average over the simulated seasons">Pts</th>
        <th class="lt-chance" title="Chance of finishing top">1st</th>${cols.map(([d, c]) => `<th title="${escapeHtml(d)}"><i class="lt-zone" style="background:${c}"></i></th>`).join("")}</tr></thead>
      <tbody>${list.map((x, i) => `<tr><td class="lt-pos" style="border-left-color:${zones.get(byRank.get(i + 1)) || "transparent"}">${i + 1}</td>
          <td class="lt-badge">${clubCrest(x.r.team, "club-logo", `data-club="${x.r.team}"`)}</td>
          <td class="lt-club">${clubLink(x.r.team, data.teams[x.r.team] || teamName(x.r.team))}</td>
          <td class="lt-wide">${x.left}</td><td class="lt-wdl">${Math.round(x.w)}</td><td class="lt-wdl">${Math.round(x.d)}</td><td class="lt-wdl">${Math.round(x.l)}</td>
          <td class="lt-gd">${x.gd >= 0.5 ? "+" : ""}${Math.round(x.gd)}</td><td><b>${Math.round(x.pts)}</b></td>
          <td class="lt-chance">${pct(x.pos[0])}</td>${cols.map(([, , places]) => `<td>${pct(places.reduce((a, k) => a + (x.pos[k] || 0), 0))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  };
  return groups.map(table).join("") + zoneLegend(zones)
    + `<div class="page-note">The ${upcoming.length.toLocaleString()} scheduled matches left, played out ${SIMS.toLocaleString()} times from the model's predicted scores and home · draw · away chances, on top of the current table. Each simulated season also varies every club's true strength a little, since ratings are estimates and a club that is better or worse than rated is so all season. The figures are chances, not a forecast of one outcome. Level clubs are split by goal difference, then goals scored. Matches not yet scheduled (play-offs, split rounds) aren't included.</div>`;
}

// ---- Matches: one round at a time, opening on the round with the next fixture
function leagueMatchesTab() {
  const { data } = state.league;
  const fx = data.fixtureRows;
  if (!fx.length) return `<div class="empty-state">No fixtures yet this season.</div>`;
  const rounds = [...new Set(fx.map((f) => f.round))];
  if (!rounds.includes(state.league.round)) {
    const upcoming = fx.find((f) => !FINISHED.has(f.status) && !OFF.has(f.status));
    state.league.round = upcoming ? upcoming.round : rounds[rounds.length - 1];
  }
  const i = rounds.indexOf(state.league.round);
  const preds = new Map(state.data.matches.map((m) => [m.id, m]));
  const name = (t) => data.teams[t] || teamName(t);
  const byDay = new Map();
  for (const f of fx.filter((f) => f.round === state.league.round)) {
    const day = localDateStr(new Date(f.kickoff));
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push(f);
  }
  const logo = (t) => clubCrest(t, "club-logo", `data-club="${t}"`);
  const row = (f) => {
    const done = f.hg != null && (FINISHED.has(f.status) || LIVE.has(f.status));
    const p = preds.get(f.id);
    const mid = done ? `<b>${f.hg}–${f.ag}</b>${f.pen_h != null ? `<span class="lf-note">${f.pen_h}–${f.pen_a} pens</span>` : ""}`
      : OFF.has(f.status) ? `<span class="lf-note">${f.status === "PST" ? "Postponed" : f.status === "CANC" ? "Cancelled" : "Abandoned"}</span>`
      : escapeHtml(fmtTime(f.kickoff));
    const won = (a, b) => done && FINISHED.has(f.status) && a > b ? " lf-win" : "";
    return `<div class="lf-row">
      <div class="lf-team lf-home${won(f.hg, f.ag)}">${clubLink(f.home, name(f.home))}${logo(f.home)}</div>
      <div class="lf-mid${LIVE.has(f.status) ? " lf-live" : ""}">${mid}</div>
      <div class="lf-team${won(f.ag, f.hg)}">${logo(f.away)}${clubLink(f.away, name(f.away))}</div>
      ${!done && p?.p_home != null ? `${p.home_xg != null ? `<div class="lf-sub" title="The model's expected goals for each side">${p.home_xg.toFixed(1)}–${p.away_xg.toFixed(1)}</div>` : ""}<div class="lf-sub">${Math.round(p.p_home * 100)}% · ${Math.round(p.p_draw * 100)}% · ${Math.round(p.p_away * 100)}%</div>` : ""}
    </div>`;
  };
  return `
    <div class="round-nav">
      <button type="button" class="filter-chip" data-round-step="-1" ${i <= 0 ? "disabled" : ""} aria-label="Previous round">‹</button>
      <select id="round-select" aria-label="Round">${rounds.map((r) => `<option value="${escapeHtml(r)}"${r === state.league.round ? " selected" : ""}>${escapeHtml(roundLabel(r))}</option>`).join("")}</select>
      <button type="button" class="filter-chip" data-round-step="1" ${i >= rounds.length - 1 ? "disabled" : ""} aria-label="Next round">›</button>
    </div>
    ${[...byDay.values()].map((list) => `<div class="modal-section">${escapeHtml(fmtDay(list[0].kickoff))}</div>${list.map(row).join("")}`).join("")}`;
}

// ---- Strength ranking: the league's clubs by Baseline Strength, with their actual table position
function leagueClubsTab() {
  const { id, data } = state.league;
  const pos = new Map(data.tableRows.map((r) => [r.team, r.rank]));
  const rows = leagueRanked(id, data);
  if (!rows.length) return `<div class="empty-state">No ranked clubs.</div>`;
  return clubRatingTable(rows, data.tableRows.length ? (r) => pos.get(r.team) ?? "" : null, data.teams, null, leagueSort("clubs", STRENGTH_COLS, "lt"))
    + `<div class="page-note">Baseline: Baseline Strength, the long-term Elo rating. Current: Current Strength, the Elo rating now. Gap: Current minus Baseline. Last 6: the change in Elo over the club's last 6 matches.</div>`;
}

// clubs table for the league and country pages; pos = the table position column (Pl when null).
// sort (a { key, dir } kept by the page): headers sort it, # stays each club's Baseline Strength rank
const STRENGTH_COLS = {
  rank: { dir: 1, val: (r) => r.i }, club: { dir: 1, val: (r) => r.name }, pos: { dir: 1, val: (r) => r.pos === "" ? null : r.pos },
  played: { dir: -1, val: (r) => r.played }, lt: { dir: -1, val: (r) => r.lt }, trend: { dir: -1, val: (r) => r.trend },
  current: { dir: -1, val: (r) => r.current }, form: { dir: -1, val: (r) => r.form },
};
function clubRatingTable(rows, pos, names = {}, meta = null, sort = null, limit = Infinity) {
  const sortable = !!sort, s = sort || { key: null };
  const th = (key, label, title, cls = "") => sortable ? sortTh("clubs", s, key, label, title, cls)
    : `<th${cls ? ` class="${cls}"` : ""} title="${escapeHtml(title)}">${label}</th>`;
  let list = rows.map((r, i) => ({ r, i: i + 1, name: names[r.team] || teamName(r.team), pos: pos ? pos(r) : null,
    played: r.played, lt: r.lt, trend: r.trend, current: r.current, form: r.form }));
  if (sortable) list = sortLeagueRows(list, s, STRENGTH_COLS);
  list = list.slice(0, limit);
  return `<div class="table-scroll"><table class="leaderboard clubs">
    <thead><tr>${th("rank", "#", "Baseline Strength rank")}<th></th>${th("club", "Club", "Club name")}${pos ? th("pos", "Table", "Actual position in the competition's table", "num") : th("played", "Pl", "Matches rated", "num")}
      ${th("lt", BASELINE_TH, "Baseline Strength: long-term Elo", "num")}${th("trend", "Gap", "Current minus Baseline", "num col-gap")}${th("current", "Current", "Current Strength: Elo now", "num")}${th("form", "Last 6", "Elo change over the last 6 matches", "num col-recent")}</tr></thead>
    <tbody>${list.map(({ r, i, name, pos: p }) => `<tr>
      <td>${i}</td>
      <td>${clubCrest(r.team, "club-logo", `data-club="${r.team}"`)}</td>
      <td>${clubLink(r.team, name)}${meta ? meta(r) : ""}</td>
      <td class="num" style="color:var(--text-muted)">${pos ? p : r.played}</td>
      <td class="num">${eloChip(r.lt)}</td>
      <td class="num col-gap">${formHtml(r.trend)}</td>
      <td class="num">${formChip(r.current)}</td>
      <td class="num col-recent">${formHtml(r.form)}</td></tr>`).join("")}</tbody></table></div>`;
}

$("#club-body").addEventListener("click", (e) => {
  const countrySort = state.country && e.target.closest("#country-clubs [data-lsort]");
  if (countrySort) {
    const key = countrySort.dataset.lsort.split(":")[1], s = state.country.sort;
    if (s.key === key) s.dir = -s.dir; else Object.assign(s, { key, dir: STRENGTH_COLS[key].dir });
    return renderCountryClubs();
  }
  if (!state.league || !$("#league-tab")) return;
  const t = e.target.closest("[data-ltab]");
  if (t) {
    state.league.tab = t.dataset.ltab;
    history.replaceState(null, "", `${leagueHref(state.league.id)}/${state.league.tab}`);   // shareable, no history entry
    return renderLeagueTab();
  }
  const sortBy = e.target.closest("[data-lsort]");
  if (sortBy) {
    const [tab, key] = sortBy.dataset.lsort.split(":");
    const cols = tab === "table" ? STANDINGS_COLS : STRENGTH_COLS, s = state.league.sort[tab];
    if (s.key === key) s.dir = -s.dir; else Object.assign(s, { key, dir: cols[key].dir });
    return renderLeagueTab();
  }
  const step = e.target.closest("[data-round-step]");
  if (step) {
    const rounds = [...new Set(state.league.data.fixtureRows.map((f) => f.round))];
    state.league.round = rounds[rounds.indexOf(state.league.round) + Number(step.dataset.roundStep)] ?? state.league.round;
    renderLeagueTab();
  }
});
$("#club-body").addEventListener("change", (e) => {
  if (e.target.id === "round-select" && state.league) { state.league.round = e.target.value; renderLeagueTab(); }
});

// ---- Country: its leagues (strongest first), cups and clubs
function openCountryPage(country) {
  showPage(countryDisplay(country));
  state.club = null;
  const body = $("#club-body");
  const name = countryDisplay(country);
  const comps = Object.entries(state.data.competitions).filter(([, c]) => c.country === country && c.type !== "International")
    .map(([lid, c]) => ({ lid: Number(lid), ...c }));
  if (!comps.length) { body.innerHTML = `<div class="empty-state">No competitions for ${escapeHtml(name)}.</div>`; return; }
  const leagues = comps.filter((c) => c.type === "League").map((c) => {
    const clubs = leagueClubs(c.lid);
    return { ...c, clubs, avg: avgRating(clubs) };
  }).sort((a, b) => (b.avg ?? -1) - (a.avg ?? -1));
  const order = (lid) => { const k = GROUP_ORDER.indexOf(lid); return k < 0 ? 999 : k; };
  const cups = comps.filter((c) => c.type !== "League").sort((a, b) => order(a.lid) - order(b.lid));
  const clubs = leagues.flatMap((c) => c.clubs).sort((a, b) => b.lt - a.lt);
  const avg = avgRating(clubs.slice(0, 15));   // the country's level: its 15 best clubs
  const card = (c) => `<a class="lg-card" href="${leagueHref(c.lid)}">
      ${leagueCrest(c.lid)}
      <span class="lg-main"><span class="lg-name">${escapeHtml(c.name)}</span>
        ${c.clubs?.length ? `<span class="lg-sub">${c.clubs.length} clubs · top rated ${escapeHtml(teamName(c.clubs[0].team))}</span>` : ""}</span>
      ${c.avg != null ? `<span class="rel-chip rel-${ratingTierOf(c.avg)}" title="Average Baseline Strength of its clubs">${Math.round(c.avg)}</span>` : ""}</a>`;
  const LIMIT = 50;
  const meta = leagues.length > 1 ? (r) => ` <span class="club-meta">${leagueLink(r.league)}</span>` : null;
  const count = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  body.innerHTML = `
    <div class="pl-hero">
      ${FLAG_CODES[name] ? `<img class="country-flag-lg" src="https://flagcdn.com/w160/${FLAG_CODES[name]}.png" alt="">` : "<span></span>"}
      <div class="pl-hero-main">
        <h2>${escapeHtml(name)}</h2>
        <div class="pl-hero-club"><span class="pl-meta">${[leagues.length && count(leagues.length, "league"), cups.length && count(cups.length, "cup"),
          clubs.length && count(clubs.length, "club")].filter(Boolean).join(" · ")}</span></div>
      </div>
      ${avg != null ? `<div class="pl-hero-rank rel-${ratingTierOf(avg)}" title="Average Baseline Strength (long-term Elo) of the 15 best clubs in its leagues">
        <span class="val">${Math.round(avg)}</span></div>` : ""}
    </div>
    ${leagues.length ? `<div class="modal-section" style="margin-top:0">Leagues</div><div class="lg-list">${leagues.map(card).join("")}</div>
      ${leagues.length > 1 ? `<div class="page-note">Strongest first, by the average Baseline Strength of their clubs.</div>` : ""}` : ""}
    ${cups.length ? `<div class="club-section"${leagues.length ? "" : ' style="margin-top:0"'}><div class="modal-section">${leagues.length ? "Cups" : "Competitions"}</div>
      <div class="lg-list">${cups.map(card).join("")}</div></div>` : ""}
    ${clubs.length ? `<div class="club-section"><div class="modal-section">Clubs</div><div id="country-clubs"></div>
      ${clubs.length > LIMIT ? `<button type="button" class="show-all" id="country-more">Show all ${clubs.length.toLocaleString()}</button>` : ""}</div>` : ""}`;
  // sorted by Current Strength to start; # stays the Baseline Strength rank
  state.country = { clubs, meta, limit: LIMIT, sort: { key: "current", dir: STRENGTH_COLS.current.dir } };
  if (clubs.length) renderCountryClubs();
  $("#country-more")?.addEventListener("click", (e) => {
    state.country.limit = Infinity;
    renderCountryClubs();
    e.target.remove();
  });
}
// the top LIMIT by the chosen sort (all of them once "Show all" is clicked)
function renderCountryClubs() {
  const { clubs, meta, limit, sort } = state.country;
  $("#country-clubs").innerHTML = clubRatingTable(clubs, null, {}, meta, sort, limit);
}

// ------------------------------------------------------------------ Leagues
// Every league with rated clubs, laid out like the Clubs ranking: strongest first by the average
// Baseline Strength of its clubs (the number on each league page), or by another column
function renderLeagues() {
  const body = $("#leagues-body");
  if (!state.rankings) { body.innerHTML = `<div class="empty-state">Loading leagues…</div>`; return; }
  const avgOf = (rows, k) => rows.reduce((t, r) => t + r[k], 0) / rows.length;
  const key = state.leaguesSort ||= "lt";
  const leagues = Object.entries(state.data.competitions).filter(([, c]) => c.type === "League").map(([lid, c]) => {
    const clubs = leagueClubs(Number(lid));
    if (!clubs.length) return null;
    const lt = avgOf(clubs, "lt"), current = avgOf(clubs, "current");
    return { lid: Number(lid), ...c, clubs: clubs.length, lt, current, trend: Math.round(current) - Math.round(lt) };
  }).filter(Boolean).sort((a, b) => b[key] - a[key] || b.lt - a.lt);
  if (!leagues.length) { body.innerHTML = `<div class="empty-state">No leagues yet.</div>`; return; }
  const th = (k, label, tip, cls = "") =>
    `<th class="num sortable${key === k ? " active" : ""}${cls}" tabindex="0"${key === k ? ` aria-sort="descending"` : ""} data-lgsort="${k}" title="${escapeHtml(tip + " Click to sort.")}">${label}</th>`;
  body.innerHTML = `
    <div class="table-scroll"><table class="leaderboard clubs">
      <thead><tr>
        <th title="Position in this list, in the current sort order.">#</th>
        <th><span class="th-club">League</span></th>
        <th title="League name and its country's flag. Click a league to open its page.">League</th>
        ${th("clubs", "Clubs", "Rated clubs playing in the league this season.")}
        ${th("lt", BASELINE_TH, "Average Baseline Strength (long-term Elo) of the league's clubs: the number on the league's page.")}
        ${th("trend", "Gap", "Average Current Strength minus average Baseline Strength. Green: the league's clubs are rated above their long-term level; red: below it.", " col-gap")}
        ${th("current", "Current", "Average Current Strength (Elo now) of the league's clubs.")}
      </tr></thead>
      <tbody>${leagues.map((c, i) => `
        <tr>
          <td>${i + 1}</td>
          <td><a href="${leagueHref(c.lid)}" aria-label="${escapeHtml(c.name)}">${leagueCrest(c.lid)}</a></td>
          <td><div class="club-cell"><a class="team-link" href="${leagueHref(c.lid)}">${escapeHtml(c.name)}</a>
            ${FLAG_CODES[countryDisplay(c.country)] ? `<span class="club-meta">${flagLink(c.country)}</span>` : ""}</div></td>
          <td class="num" style="color:var(--text-muted)">${c.clubs}</td>
          <td class="num"><span class="rel-chip rel-${ratingTierOf(c.lt)}">${Math.round(c.lt)}</span></td>
          <td class="num col-gap">${formHtml(c.trend)}</td>
          <td class="num">${formChip(c.current)}</td>
        </tr>`).join("")}
      </tbody>
    </table></div>
    <div class="page-note">Averages over the clubs playing in each league this season.</div>`;
  fitClubMeta(body);
  clubTableObserver.observe(body.querySelector(".table-scroll"));
}
$("#leagues-body").addEventListener("click", (e) => {
  const th = e.target.closest("th[data-lgsort]");
  if (!th) return;
  state.leaguesSort = th.dataset.lgsort;
  renderLeagues();
});

// ------------------------------------------------------------------ Nations
// The national team ranking (data/nations.json, from nations.py): the club Elo run over every men's
// international since 1872. Loaded the first time the tab opens.
const CONFEDS = ["UEFA", "CONMEBOL", "CONCACAF", "CAF", "AFC", "OFC"];
function loadNations() {
  if (state.nations !== undefined) return state.nationsLoading;
  state.nations = null;
  return state.nationsLoading = getJsonOrNull("data/nations.json").then((d) => {
    if (d) for (const n of d.nations) n.change = n.year_ago == null ? null : n.current - n.year_ago;
    state.nations = d || false;
    renderNations();
  });
}
// A rating's place among the nations, as the badge colours: top 5% green, 20% amber, half orange
function nationTier(d, v) {
  const share = (d.nations.filter((n) => n.current > v).length + 1) / d.nations.length;
  return share <= 0.05 ? 4 : share <= 0.2 ? 3 : share <= 0.5 ? 2 : 1;
}
// A nationality page's nation in the ranking (API-Football's name or the dataset's)
const nationFor = (d, nat) => d.nations.find((x) => x.name === nat || (d.aliases?.[x.name] || []).includes(nat));
// The top right of a nationality page: the national team's current Elo, once the ranking has loaded
async function fillNationRating(nat) {
  await loadNations();
  const el = $("#nat-elo"), d = state.nations;
  if (!el || el.dataset.nat !== nat || !d) return;
  const n = nationFor(d, nat);
  if (!n) return;
  const rank = d.nations.filter((x) => x.current > n.current).length + 1;
  el.outerHTML = heroRank(n.current, "", nationTier(d, n.current),
    `National team Elo rating: world #${rank} of ${d.nations.length}${n.change != null ? ` · ${n.change >= 0 ? "+" : ""}${Math.round(n.change)} on a year ago` : ""}`);
}
// The nationality page's name for a nation (API-Football's), if we have players from it
function nationPageName(n, aliases) {
  const nats = state.natSet ||= new Set((state.players?.list || []).map((p) => p.nationality));
  return [n.name, ...(aliases[n.name] || [])].find((x) => nats.has(x));
}
function renderNations() {
  const body = $("#nations-body");
  const d = state.nations;
  if (d == null || (d && state.players === undefined)) { body.innerHTML = `<div class="empty-state">Loading nations…</div>`; return; }
  if (!d) { body.innerHTML = loadFailed("nations") ? loadError("the nations ranking") : `<div class="empty-state">No national team ranking yet.</div>`; return; }
  const key = state.nationsSort ||= "current";
  const confed = state.nationsConfed ||= "all";
  const worldRank = new Map([...d.nations].sort((a, b) => b.current - a.current).map((n, i) => [n.name, i + 1]));
  const rows = d.nations.filter((n) => confed === "all" || n.confed === confed)
    .sort((a, b) => (b[key] ?? -Infinity) - (a[key] ?? -Infinity) || b.current - a.current);
  // badge colours as for clubs, but placed among the nations: top 5% green, 20% amber, half orange
  const tier = (v) => nationTier(d, v);
  const chip = (value, label) => `<button type="button" class="filter-chip" data-confed="${value}" aria-pressed="${confed === value}">${label}</button>`;
  const th = (k, label, tip, cls = "") =>
    `<th class="num sortable${key === k ? " active" : ""}${cls}" tabindex="0"${key === k ? ` aria-sort="descending"` : ""} data-natsort="${k}" title="${escapeHtml(tip + " Click to sort.")}">${label}</th>`;
  const score = (l) => `${l.gf}–${l.ga} v ${l.opp}`;
  body.innerHTML = `
    <div class="filter-row" style="margin-bottom:10px">${chip("all", "World")}${CONFEDS.map((c) => chip(c, c)).join("")}</div>
    <div class="table-scroll"><table class="leaderboard clubs">
      <thead><tr>
        <th title="Position in this list, in the current sort order.">#</th>
        <th><span class="th-club">Nation</span></th>
        <th title="The national team and its confederation. Hover for its last 12 months and last match.">Nation</th>
        ${th("current", "Current", "Current Strength: the Elo rating now. 100 points is about one goal a game on a neutral ground.")}
        ${th("change", "1 yr", "Change in Current Strength over the last 12 months.")}
      </tr></thead>
      <tbody>${rows.map((n, i) => {
        const page = nationPageName(n, d.aliases || {});
        const name = page ? `<a class="team-link" href="#/nation/${encodeURIComponent(page)}">${escapeHtml(n.name)}</a>` : `<span class="team-link">${escapeHtml(n.name)}</span>`;
        const tip = `World #${worldRank.get(n.name)} · Last 12 months: ${n.w}W ${n.d}D ${n.l}L · Last match: ${score(n.last)} (${n.last.comp}, ${fmtShortDate(n.last.date)} ${n.last.date.slice(0, 4)}) · ${n.played} internationals rated`;
        return `
        <tr title="${escapeHtml(tip)}">
          <td>${i + 1}</td>
          <td>${/^[a-z]{2}(-[a-z]{3})?$/.test(n.flag) ? `<img class="flag" src="https://flagcdn.com/w40/${n.flag}.png" alt="" loading="lazy" data-broken="remove">` : ""}</td>
          <td><div class="club-cell">${name}${n.confed ? ` <span class="club-meta">${escapeHtml(n.confed)}</span>` : ""}</div></td>
          <td class="num"><span class="rel-chip rel-${tier(n.current)}">${Math.round(n.current)}</span></td>
          <td class="num">${formHtml(n.change)}</td>
        </tr>`; }).join("")}
      </tbody>
    </table></div>
    <div class="page-note">Elo ratings from every men's full international since 1872 (${d.matches.toLocaleString()} matches, the latest on ${fmtShortDate(d.latest_match)} ${d.latest_match.slice(0, 4)}), the club model's method with home advantage only away from neutral grounds. FIFA members that have played in the last four years. Results: <a href="https://github.com/martj42/international_results" rel="noopener">international_results</a>${d.from_api ? ` and API-Football (${d.from_api} recent matches)` : ""}.</div>`;
  clubTableObserver.observe(body.querySelector(".table-scroll"));
}
$("#nations-body").addEventListener("click", (e) => {
  const th = e.target.closest("th[data-natsort]");
  const chip = e.target.closest("[data-confed]");
  if (th) state.nationsSort = th.dataset.natsort;
  else if (chip) state.nationsConfed = chip.dataset.confed;
  else return;
  renderNations();
});

// ------------------------------------------------------------------ FPL findings
// The fantasy expected-points model's validation (fpl.json, from experiments/fantasy_v1). No FPL
// data is used: points are rebuilt from match stats with FPL's scoring rules.
const FPL_POS = { G: "GK", D: "DEF", M: "MID", F: "FWD" };
const FPL_NAMES = { model: "Our model", recent5: "Last-5 average", ppg: "Points per game",
  flat_team_goals: "Our model, no match model", v1_1: "v1.1 (next version)" };
function renderFpl() {
  state.drawn.add("fpl");
  const body = $("#fpl-body");
  const f = state.fpl;
  if (!f) { body.innerHTML = `<div class="empty-state">No FPL findings yet.</div>`; return; }
  const o = f.overall, n2 = (x) => x == null ? "–" : x.toFixed(2), n3 = (x) => x == null ? "–" : x.toFixed(3);
  const passed = f.criteria.filter((c) => c.pass).length;
  const byKey = Object.fromEntries(f.criteria.map((c) => [c.key, c]));
  const card = (label, value, note = "") =>
    `<div class="stats-card"><div class="stats-label">${label}</div><div class="stats-value">${value}</div>${note ? `<div class="stats-note">${note}</div>` : ""}</div>`;
  const ci = (d) => `${d.diff > 0 ? "+" : "−"}${Math.abs(d.diff).toFixed(3)} (95% range ${d.lo.toFixed(3)} to ${d.hi.toFixed(3)})`;
  const pctSigned = (x) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(Math.abs(x) < 10 ? 1 : 0)}%`;
  const badge = (ok) => `<span class="fpl-badge ${ok ? "pass" : "fail"}">${ok ? "PASS" : "FAIL"}</span>`;
  const b = byKey.bias, cal = byKey.calibration;
  const checks = [
    [byKey.benchmarks.pass, `<b>Beats the simple guesses.</b> Lower average error than both the last-5 average and points per game, and the gap is clear of noise: ${ci(byKey.benchmarks.mae_vs_recent)} points per player vs last-5 average.`],
    [b.pass, `<b>Predicts the right amount of points.</b> Overall ${pctSigned(b.overall_bias_pct)} (limit ±5%), but goalkeepers ${pctSigned(b.position_bias_pct.G)} (limit ±10%): save points were left out after failing their own check (see below).`],
    [cal.pass, `<b>Its probabilities are honest.</b> Start chances off by ${pct(cal.start_ece)} on average, clean-sheet chances by ${pct(cal.team_cs_ece)} (limit 3%).`],
    [byKey.match_model.pass, `<b>The match model earns its place.</b> Using our match predictions instead of league-average goals lowers the error by ${Math.abs(byKey.match_model.mae_vs_flat.diff).toFixed(3)}.`],
  ].map(([ok, text]) => `${badge(ok)}<span>${text}</span>`).join("");
  const benchRows = ["model", "recent5", "ppg", "flat_team_goals", "v1_1"].map((k) =>
    `<tr${k === "model" ? ' class="fpl-hl"' : ""}><td>${FPL_NAMES[k]}${k === "v1_1" ? " *" : ""}</td><td>${n3(o[k].mae)}</td><td>${n3(o[k].rmse)}</td>
      <td>${n2(o[k].spearman)}</td><td>${pct(f.top_n[k].top10.hit_rate, 0)}</td><td>${n2(f.top_n[k].top10.mean_points)}</td></tr>`).join("");
  const segTable = (seg, label, order, fmt = (g) => g) => {
    const rows = order.filter((g) => seg[g]).map((g) => {
      const x = seg[g], better = x.model.mae < x.recent5.mae;
      return `<tr><td>${fmt(g)}</td><td>${x.model.n.toLocaleString()}</td><td class="${better ? "gap-ok" : "gap-off"}">${n3(x.model.mae)}</td>
        <td>${n3(x.recent5.mae)}</td><td>${n3(x.ppg.mae)}</td><td>${n2(x.model.spearman)}</td><td>${n2(x.recent5.spearman)}</td></tr>`;
    }).join("");
    return `<div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table"><thead><tr><th>${label}</th><th>Rows</th><th>Model err</th><th>Last-5 err</th><th>PPG err</th><th>Model rank</th><th>Last-5 rank</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  };
  const posTop = ["G", "D", "M", "F"].map((p) => {
    const key = `${p}_top${p === "G" || p === "F" ? 5 : 10}`;
    return `<tr><td>${FPL_POS[p]} top ${p === "G" || p === "F" ? 5 : 10}</td>${["model", "recent5", "ppg", "flat_team_goals"].map((k) =>
      `<td>${pct(f.top_n[k][key].hit_rate, 0)}</td>`).join("")}</tr>`;
  }).join("");
  const calibRows = (c) => c.bins.map(([count, p, rate], i) => {
    const gap = Math.abs(rate - p);
    return `<tr><td>${pct(p, 0)}</td><td>${count.toLocaleString()}</td><td class="${gap <= 0.03 ? "gap-ok" : gap > 0.06 ? "gap-off" : ""}">${pct(rate, 0)}</td>
      <td style="width:70px"><span class="calib-bar" style="width:${Math.round(rate * 60)}px"></span></td></tr>`;
  }).join("");
  const mi = f.minutes, reg = f.segments.regular.regular, pr = f.prospective;
  const liveText = pr.state === "not_started" ? "Not started: the snapshot table hasn't been created yet."
    : pr.state === "waiting" ? "Ready: the first snapshots are taken before the next Premier League round."
    : `Capturing since ${new Date(pr.first_capture).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}: ${pr.finished_fixtures} finished matches so far.`;
  const rounds = pr.finished_rounds || 0;
  body.innerHTML = `
    <details class="stats-card fpl-verdict${passed === f.criteria.length ? " ok" : ""}">
      <summary><span class="stats-label">Model status</span>
        <span class="fpl-verdict-line">${passed === f.criteria.length ? "Validated" : "Promising, not yet validated"} · ${passed} of ${f.criteria.length} checks pass</span></summary>
      <p class="fpl-text">Our model predicts each Premier League player's fantasy points per match from expected minutes, our match predictions,
        each player's shots and chances, and clean-sheet odds. Tested on ${f.test.rows.toLocaleString()} player-matches since July 2024 that it had never seen,
        it beats the usual shortcuts clearly and its probabilities are well calibrated. It fails one check: goalkeepers come out too low because save points were left out.
        The predictions below use a later version (v1.4), which adds saves, injury news, bonus, cards, penalty saves and defensive contributions.
        It was designed after seeing these results, so it is now being tested on upcoming gameweeks before anyone should rely on it.</p>
    </details>
    <div class="stats-card" id="fpl-next"></div>
    <div class="stats-grid">
      ${card("Average error", `${n2(o.model.mae)} pts`, `Last-5 average: ${n2(o.recent5.mae)} · points per game: ${n2(o.ppg.mae)}`)}
      ${card("Rounds won", `${f.round_wins.model_lower_mae} / ${f.round_wins.rounds}`, "Rounds where it beat the last-5 average")}
      ${card("Top-10 picks that hit", pct(f.top_n.model.top10.hit_rate, 0), `Last-5 average: ${pct(f.top_n.recent5.top10.hit_rate, 0)}. Hits = reached that round's actual top 10`)}
      ${card("Regular starters", `${n2(reg.model.mae)} pts`, `Error for players starting 3+ of the last 5. Last-5 average: ${n2(reg.recent5.mae)}`)}
    </div>
    <div class="stats-card">
      <div class="stats-label">The checks, set before testing</div>
      <div class="fpl-checks">${checks}</div>
    </div>
    <div class="stats-card">
      <div class="stats-label">Against simple benchmarks</div>
      <div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table">
        <thead><tr><th>Predictor</th><th>Avg error</th><th>RMSE</th><th>Rank corr.</th><th>Top-10 hit</th><th>Top-10 pts</th></tr></thead>
        <tbody>${benchRows}</tbody></table></div>
      <div class="stats-note">Average error is points per player per match (lower is better). Rank correlation: 1 = perfect ordering.
        Single-match fantasy points are mostly luck, so even a good model is often wrong about individual players.
        * v1.1 was chosen after seeing these results, so its row is not evidence: only the live test below can show it works.</div>
    </div>
    <div class="stats-card">
      <div class="stats-label">By position</div>
      ${segTable(f.segments.position, "Position", ["G", "D", "M", "F"], (g) => FPL_POS[g])}
      <div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table" style="margin-top:10px">
        <thead><tr><th>Best picks each round</th><th>Model</th><th>Last-5</th><th>PPG</th><th>No match model</th></tr></thead>
        <tbody>${posTop}</tbody></table></div>
      <div class="stats-note">Green error: the model beat the last-5 average. The match model helps most for defenders and goalkeepers, whose points depend on the opponent.</div>
    </div>
    <div class="stats-card">
      <div class="stats-label">Minutes: will he play?</div>
      <div class="vs-market">
        <span></span><span class="hd">Model</span><span class="hd">Last-5 avg</span>
        <span>Average error (mins)</span><span class="num${mi.mae < mi.recent5_mae ? " better" : ""}">${mi.mae.toFixed(1)}</span><span class="num${mi.recent5_mae < mi.mae ? " better" : ""}">${mi.recent5_mae.toFixed(1)}</span>
        <span>RMSE (mins)</span><span class="num${mi.rmse < mi.recent5_rmse ? " better" : ""}">${mi.rmse.toFixed(1)}</span><span class="num${mi.recent5_rmse < mi.rmse ? " better" : ""}">${mi.recent5_rmse.toFixed(1)}</span>
      </div>
      <div class="stats-note">An honest miss: on plain average error the simple last-5 average is slightly better, because minutes are nearly all-or-nothing and
        a 90%-likely starter is best predicted as ~76 minutes, not 90. With injury news the model's error drops to ${f.availability_minutes_mae.toFixed(1)} minutes.</div>
      <div class="stats-label" style="margin-top:12px">Chance of starting: said vs happened</div>
      <table class="calib-table"><thead><tr><th>Said</th><th>Players</th><th>Started</th><th></th></tr></thead><tbody>${calibRows(f.start_calibration)}</tbody></table>
    </div>
    <div class="stats-card">
      <div class="stats-label">Clean sheets: said vs happened</div>
      <table class="calib-table"><thead><tr><th>Said</th><th>Team games</th><th>Kept one</th><th></th></tr></thead><tbody>${calibRows(f.clean_sheet_calibration)}</tbody></table>
      <div class="stats-note">From the same goal predictions as the Matches tab. In the high-scoring 2023/24 season clean sheets were over-predicted
        (off by ${pct(f.validation_clean_sheet_ece)}), so this inherits the match model's season-to-season swings.</div>
    </div>
    <div class="stats-card">
      <div class="stats-label">Why goalkeepers fail</div>
      <p class="fpl-text">Save points were tested on 2023/24 first and missed their ±10% limit for the busiest keepers
        (${f.saves.validation_terciles[2].mean_pred.toFixed(2)} predicted vs ${f.saves.validation_terciles[2].mean_actual.toFixed(2)} actual saves), so, as agreed in advance, they were dropped.
        Without them goalkeepers are ${pctSigned(b.position_bias_pct.G)}; with them they would have been ${pctSigned(f.saves.posthoc_gk_bias)}. v1.1 puts saves back and has to prove it on new matches.</p>
    </div>
    <div class="stats-card">
      <div class="stats-label">Through the season</div>
      ${segTable(f.segments.round_bucket, "Rounds", ["1-5", "6-19", "20-38"])}
      <div class="stats-label" style="margin-top:12px">By player level (our player rank, not FPL price)</div>
      ${segTable(f.segments.ability_band, "Rank", ["80+", "70-80", "60-70"])}
    </div>
    <div class="stats-card">
      <div class="stats-label">Live test on upcoming gameweeks</div>
      <div class="stats-value">${rounds} / ${pr.target_rounds} <span style="font-size:14px;color:var(--text-muted)">rounds</span></div>
      <div class="dist-row"><span class="dist-bar-wrap"><span class="dist-bar" style="display:block;width:${Math.min(100, 100 * rounds / pr.target_rounds).toFixed(0)}%;background:var(--series-blue)"></span></span></div>
      <div class="stats-note">${liveText} Every player's prediction is saved before kickoff and can't be changed afterwards. Results stay sealed until
        ${pr.target_rounds} rounds are in, then the same checks are run once. This count is v1.1's; later versions' predictions are saved the same way and checked separately.</div>
    </div>
    <div class="stats-card">
      <div class="stats-label">What this doesn't show yet</div>
      <ul class="fpl-list">
        <li>No comparison with FPL's own expected points yet. FPL prices, positions and points are collected nightly from 28 Sept 2026, so this becomes possible from here on.</li>
        <li>Points are rebuilt from match stats with FPL's scoring rules, without bonus points, own goals, penalty misses or defensive-contribution points.</li>
        <li>Positions are from match data (GK/DEF/MID/FWD), which can differ from FPL's listing for some players.</li>
        <li>The match predictions used for past seasons were rebuilt afterwards, not made before kickoff.</li>
      </ul>
      <div class="stats-note">The Corner FC is not affiliated with the Premier League or Fantasy Premier League.</div>
    </div>`;
  renderFplNext();
}

// Predictions: each player's expected points by gameweek (fpl_predictions.json, loaded when the
// FPL tab first opens). One gameweek at a time (◀ ▶) or totals over the next 2 / 5 / 10.
const FPL_STATUS = { i: "Injured", s: "Suspended", u: "Unavailable", n: "Not in squad" };
const FPL_SHOWN = 30;
// Where a player's points come from (part_fields in the predictions file)
const FPL_PARTS = { appearance: "Minutes", goal: "Goals", penalty: "Penalties", assist: "Assists", fpl_assist: "FPL assists",
  clean_sheet: "Clean sheet", goals_conceded: "Goals conceded", save: "Saves", penalty_save: "Penalty saves", card: "Cards", bonus: "Bonus",
  dc: "Defensive contributions" };
function loadFplPredictions() {
  if (state.fplPred !== undefined) return;
  state.fplPred = null;
  Promise.all([getJsonOrNull("data/fpl_predictions.json"), loadPlayers()]).then(([d]) => { state.fplPred = d || false; renderFplNext(); });
}
function fplRows() {
  const d = state.fplPred;
  if (d.rows) return d.rows;
  return d.rows = d.players.map((r, i) => {
    const p = Object.fromEntries(d.fields.map((k, j) => [k, r[j]]));
    p.name = decodeEntities(p.name);
    p.pos = p.fpl_position || p.position;
    p.cells = d.cells[i].map((c) => Object.fromEntries(d.cell_fields.map((k, j) => [k, c[j]])));
    return p;
  });
}
function renderFplNext() {
  const el = $("#fpl-next");
  if (!el) return;
  const d = state.fplPred;
  if (d == null) { el.innerHTML = `<div class="stats-label">Predictions</div><div class="stats-note">Loading…</div>`; return; }
  if (!d || !d.players.length) { el.innerHTML = `<div class="stats-label">Predictions</div>${loadFailed("fpl_predictions") ? loadError("the predictions") : `<div class="stats-note">No upcoming Premier League gameweeks yet.</div>`}`; return; }
  const fp = state.fplView ||= { pos: "all", q: "", sort: "xp", all: false, mode: "gw", gw: 0 };
  const gws = d.gameweeks, n = fp.mode === "gw" ? 1 : Math.min(+fp.mode, gws.length);
  fp.gw = Math.max(0, Math.min(fp.gw, gws.length - 1));
  const span = fp.mode === "gw" ? [fp.gw] : gws.slice(0, n).map((_, i) => i);
  const team = (id) => d.teams[id]?.[0] || teamName(id), code = (id) => d.teams[id]?.[1] || team(id).slice(0, 3).toUpperCase();
  const gwLabel = (g) => d.source === "fpl" ? `GW${g.id}` : `Round ${g.id}`;
  const price = (p) => p.price == null ? null : p.price / 10;
  const q = fp.q.trim().toLowerCase();
  const rows = fplRows().map((p) => {
    const cells = p.cells.filter((c) => span.includes(c.gw));
    const sum = (k) => cells.reduce((a, c) => a + c[k], 0);
    const xp = sum("xp");
    return { p, cells, xp, minutes: sum("minutes"), goals: sum("goals"), assists: sum("assists"),
      price: price(p) ?? -1, value: price(p) ? xp / price(p) : -1 };
  }).filter((r) => (fp.pos === "all" || r.p.pos === fp.pos)
      && (!q || r.p.name.toLowerCase().includes(q) || team(r.p.team).toLowerCase().includes(q)))
    .sort((a, b) => b[fp.sort] - a[fp.sort] || b.xp - a.xp);
  const list = fp.all ? rows : rows.slice(0, FPL_SHOWN);
  const day = (iso) => new Date(iso).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  const tag = (p) => {
    const t = p.fpl_status && p.fpl_status !== "a" ? (p.fpl_status === "d" ? `${Math.round(Number(p.fpl_chance ?? 50)) || 0}%` : FPL_STATUS[p.fpl_status] || "Doubtful")
      : p.availability ? (p.availability === "Missing Fixture" ? "Out" : "Doubtful") : "";
    return t ? ` <span class="bet-tag warn" title="${p.fpl_status && p.fpl_status !== "a" ? "FPL status" : "On the injury list"}">${t}</span>` : "";
  };
  const opp = (c) => c.home ? code(c.opponent) : code(c.opponent).toLowerCase();
  // initials with the club's chip on its corner; surname (full name on hover) · position · price
  const meta = (r) => `<span class="fpl-meta"><span title="${FPL_POS[r.p.pos]}">${escapeHtml(r.p.pos)}${r.p.fpl_position ? "" : '<span title="Not matched to FPL yet: our position">*</span>'}</span>${r.price > 0 ? ` · £${r.price.toFixed(1)}` : ""}</span>`;
  const who = (r) => `<td class="fpl-player"><div class="fpl-who"><span class="fpl-face">${personChip(r.p.name)}
      ${clubCrest(r.p.team, "club-logo", `data-club="${r.p.team}" title="${escapeHtml(team(r.p.team))}"`, team(r.p.team))}</span>
      <div class="fpl-name"><div class="fpl-line"><span class="fpl-nm" title="${escapeHtml(r.p.name)}">${playerById(r.p.player) ? playerLink(r.p.player, shortName(r.p.name)) : escapeHtml(shortName(r.p.name))}</span>${meta(r)}${tag(r.p)}</div>
      <div class="fpl-match">${fp.mode === "gw" ? (r.cells.length ? r.cells.map((c) => `v ${escapeHtml(team(c.opponent))} ${c.home ? "H" : "A"}`).join(" · ") : "No match (blank)") : escapeHtml(team(r.p.team))}</div></div></div></td>`;
  // the points open a row below with where they come from, summed over the gameweeks shown
  const pts = (r) => !d.part_fields ? `<b>${r.xp.toFixed(1)}</b>`
    : `<button type="button" class="fpl-pts" data-fpl-break="${r.p.player}" aria-expanded="${fp.open === r.p.player}" title="Where the points come from"><b>${r.xp.toFixed(1)}</b></button>`;
  const breakdown = (r, cols) => {
    if (fp.open !== r.p.player || !d.part_fields) return "";
    // one line a part: name, its main figure (minutes, clean sheet chance, expected goals / assists), points
    const one = r.cells.length === 1 ? r.cells[0] : null;
    const sum = (k) => r.cells.reduce((a, c) => a + (c[k] || 0), 0);
    // v1.5 splits goals into open play and penalties (scored · missed), and adds the assists only FPL gives
    const pens = "pen_goals" in (r.cells[0] || {});
    const stat = { appearance: r.minutes, goal: (pens ? sum("np_goals") : r.goals).toFixed(2), assist: r.assists.toFixed(2),
      penalty: pens ? `${sum("pen_goals").toFixed(2)} · ${sum("pen_misses").toFixed(2)} missed` : "",
      fpl_assist: pens ? (sum("fpl_pen_assists") + sum("fpl_other_assists")).toFixed(2) : "",
      clean_sheet: one ? `${Math.round(one.p_clean_sheet * 100)}%` : "" };
    const labels = pens ? { ...FPL_PARTS, goal: "Goals (open play)" } : FPL_PARTS;
    const line = (label, figure, v) => `<div class="fpl-part"><span>${label}</span><span>${figure ?? ""}</span>
      <b class="${v < 0 ? "neg" : ""}">${v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}</b></div>`;
    const parts = d.part_fields.map((k, j) => [k, r.cells.reduce((a, c) => a + (c.parts[j] || 0), 0)]).filter(([, v]) => Math.abs(v) >= 0.005);
    return `<tr class="fpl-break"><td class="fpl-parts-cell" colspan="${cols}"><div class="fpl-parts">
      ${parts.map(([k, v]) => line(labels[k] || k, stat[k], v)).join("")}</div></td></tr>`;
  };
  const sortTh = (k, label, title = "") => `<th${title ? ` title="${title}"` : ""}><button type="button" class="fpl-sort${fp.sort === k ? " on" : ""}" data-fpl-sort="${k}" aria-pressed="${fp.sort === k}"${title ? ` aria-label="${title}"` : ""}>${label}</button></th>`;
  let head, body;
  if (fp.mode === "gw") {
    head = `<th>#</th><th>Player</th>${sortTh("xp", "Pts")}${sortTh("minutes", "Mins")}${sortTh("goals", "G", "Expected goals")}${sortTh("assists", "A", "Expected assists")}`;
    body = list.map((r, i) => `<tr><td>${i + 1}</td>${who(r)}<td>${pts(r)}</td><td>${r.minutes}</td>
      <td>${r.goals.toFixed(2)}</td><td>${r.assists.toFixed(2)}</td></tr>${breakdown(r, 6)}`).join("");
  } else {
    head = `<th>#</th><th>Player</th>${sortTh("xp", "Total")}${sortTh("value", "Pts/£m")}`
      + span.map((i) => `<th title="${day(gws[i].first_kickoff)}">${gwLabel(gws[i])}</th>`).join("");
    body = list.map((r, i) => `<tr><td>${i + 1}</td>${who(r)}<td>${pts(r)}</td>
      <td>${r.value > 0 ? r.value.toFixed(2) : "–"}</td>${span.map((g) => {
        const cs = r.cells.filter((c) => c.gw === g);
        return !cs.length ? `<td class="fpl-gw dim-text">–</td>` : `<td class="fpl-gw${cs.length > 1 ? " double" : ""}">${cs.reduce((a, c) => a + c.xp, 0).toFixed(1)}<span>${cs.map(opp).join(" ")}</span></td>`;
      }).join("")}</tr>${breakdown(r, 4 + span.length)}`).join("");
  }
  const modes = [["gw", "Gameweek"], ["2", "Next 2"], ["5", "Next 5"], ["10", "Next 10"]].map(([k, label]) =>
    `<button type="button" class="filter-chip" data-fpl-mode="${k}" aria-pressed="${fp.mode === k}">${label}</button>`).join("");
  const g = gws[fp.gw];
  const pager = fp.mode !== "gw" ? `<span class="fpl-span">${gwLabel(gws[0])}–${gwLabel(gws[n - 1]).replace(/^\D+/, "")}</span>`
    : `<span class="fpl-pager"><button type="button" class="filter-chip" data-fpl-step="-1" aria-label="Previous gameweek" ${fp.gw === 0 ? "disabled" : ""}>◀</button>
       <span class="fpl-span">${gwLabel(g)} · ${day(g.first_kickoff)}</span>
       <button type="button" class="filter-chip" data-fpl-step="1" aria-label="Next gameweek" ${fp.gw === gws.length - 1 ? "disabled" : ""}>▶</button></span>`;
  const chips = [["all", "All"], ["G", "GK"], ["D", "DEF"], ["M", "MID"], ["F", "FWD"]].map(([k, label]) =>
    `<button type="button" class="filter-chip" data-fpl-pos="${k}" aria-pressed="${fp.pos === k}">${label}</button>`).join("");
  const cols = (fp.mode === "gw" ? 6 : 4 + span.length);
  el.innerHTML = `
    <div class="stats-label">Predicted points</div>
    <div class="fpl-filters">${modes}${pager}</div>
    <div class="fpl-filters">${chips}
      <input type="search" class="table-search fpl-search" id="fpl-q" placeholder="Search players or clubs" aria-label="Search players or clubs" value="${escapeHtml(fp.q)}"></div>
    <div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table fpl-table${fp.mode === "gw" ? "" : " multi"}">
      <thead><tr>${head}</tr></thead>
      <tbody>${body || `<tr><td colspan="${cols}">No players match.</td></tr>`}</tbody></table></div>
    ${rows.length > FPL_SHOWN ? `<button type="button" class="show-all" id="fpl-more">${fp.all ? "Show fewer" : `Show all ${rows.length}`}</button>` : ""}
    <div class="stats-note">Points are our model's prediction with FPL's scoring rules for the player's FPL position: appearance, goals, penalties, assists, FPL assists, clean sheets,
      goals conceded, saves, penalty saves, cards, bonus and defensive contributions. Bonus is rebuilt from match stats (it tracks FPL's own closely).
      Defensive contributions combine each player's tackles, blocks and interceptions with his own FPL record this season, which also counts clearances.
      Penalties go mostly to each club's taker, from FPL's penalty order and who has taken them recently; a miss costs 2.
      FPL assists are the ones FPL gives that match stats don't: winning a penalty a teammate scores, and rebounds or deflections from a player's shot.
      Injuries use FPL's status: injured or suspended players are out until FPL's return date (or until FPL clears them), and doubtful players count at FPL's chance of playing for the next gameweek; match-day injury lists apply near kickoff.
      Click a player's points to see where they come from.
      ${d.source === "fpl" ? "Positions, prices, status and gameweeks come from FPL (updated nightly); players FPL doesn't list at their club are left out." : "FPL positions, prices and gameweeks appear after the first nightly FPL update; until then * marks our own position and rounds are the fixture list's."}
      In the multi-gameweek view, capitals are home games and lower case away; a double gameweek shows both. Predictions further ahead assume today's form and fitness.
      This is ${escapeHtml(d.model)}, designed after the backtest below and still being tested on upcoming gameweeks: a guide, not a pick list.</div>`;
  // multi-gameweek: # and Player freeze when the table scrolls sideways; Player's left edge is #'s width
  const table = el.querySelector(".fpl-table.multi");
  if (table) table.style.setProperty("--fz2", `${table.tHead.rows[0].cells[0].getBoundingClientRect().width}px`);
}
$("#fpl-body").addEventListener("click", (e) => {
  const t = (sel) => e.target.closest(sel);
  const pos = t("[data-fpl-pos]"), sort = t("[data-fpl-sort]"), mode = t("[data-fpl-mode]"), step = t("[data-fpl-step]");
  const brk = t("[data-fpl-break]");
  if (!pos && !sort && !mode && !step && !brk && e.target.id !== "fpl-more") return;
  const fp = state.fplView;
  if (brk) fp.open = fp.open === +brk.dataset.fplBreak ? null : +brk.dataset.fplBreak;
  if (pos) { fp.pos = pos.dataset.fplPos; fp.all = false; }
  if (sort) fp.sort = sort.dataset.fplSort;
  if (mode) { fp.mode = mode.dataset.fplMode; fp.all = false; if (fp.mode !== "gw" && (fp.sort === "minutes" || fp.sort === "goals" || fp.sort === "assists")) fp.sort = "xp"; }
  if (step) fp.gw += +step.dataset.fplStep;
  if (e.target.id === "fpl-more") fp.all = !fp.all;
  renderFplNext();
});
$("#fpl-body").addEventListener("input", (e) => {
  if (e.target.id !== "fpl-q") return;
  state.fplView.q = e.target.value;
  state.fplView.all = false;
  const at = e.target.selectionStart;
  renderFplNext();
  const box = $("#fpl-q"); box.focus(); box.setSelectionRange(at, at);
});

// ------------------------------------------------------------------ My FPL team
// The owner's FPL team (fpl_team.json, from `fpl team`) with a transfer plan and chip advice worked
// out here in the browser by assets/fpl-planner.js. "I've made these transfers" saves a lock for the
// gameweek in Supabase (README: My FPL team), and the plan then starts from the squad after them,
// until an FPL update reads the transfers from FPL itself. The key below is Supabase's public anon
// key: the database lets it read the locks and call lock/unlock_fpl_transfers, which check the
// owner's passphrase. Empty = locking not set up; the plan still shows.
const SUPABASE = { url: "https://bookkurhdabdeccckjbn.supabase.co", key: "sb_publishable_JZ_oJVHIO75SFbFc95LQew_3wmKuvM7" };
const CHIP_NAMES = { wildcard: "Wildcard", freehit: "Free Hit", bboost: "Bench Boost", "3xc": "Triple Captain" };
const CHIP_GAIN = { wildcard: "over the plan's weeks, against the plan", freehit: "that week, against the planned squad",
  bboost: "from the bench", "3xc": "from the extra captaincy" };
const storedText = (k) => { try { return localStorage.getItem(`fc.${k}`) || ""; } catch { return ""; } };
const storeText = (k, v) => { try { if (v) localStorage.setItem(`fc.${k}`, v); else localStorage.removeItem(`fc.${k}`); } catch { /* not stored */ } };

async function supabase(path, body) {
  const headers = { apikey: SUPABASE.key, "Content-Type": "application/json" };
  if (SUPABASE.key.startsWith("eyJ")) headers.Authorization = `Bearer ${SUPABASE.key}`;   // a legacy anon key (a JWT)
  const r = await fetch(`${SUPABASE.url}/rest/v1/${path}`,
    body ? { method: "POST", headers, body: JSON.stringify(body) } : { headers, cache: "no-store" });
  if (!r.ok) throw new Error(`Supabase ${r.status}`);
  return r.json();
}
function loadMyTeam() {
  if (state.myTeam) return;
  const mt = state.myTeam = { team: undefined, pred: undefined, locks: null, ft: null, key: storedText("fplKey"), note: "", msg: "" };
  Promise.all([getJsonOrNull("data/fpl_team.json"), getJsonOrNull("data/fpl_predictions.json")]).then(([team, pred]) => {
    mt.team = team || false;
    mt.pred = pred || false;
    if (team && pred) loadMyLocks();
    else renderMyTeam();
  });
}
function loadMyLocks() {
  const mt = state.myTeam, t = mt.team;
  if (!SUPABASE.key) { mt.locks = new Map(); mt.note = "Locking in isn't set up yet (README: My FPL team)."; replan(); return; }
  supabase(`fpl_team_locks?entry_id=eq.${t.entry}&season=eq.${t.season}&select=event_id,transfers,locked_at`)
    .then((rows) => { mt.locks = new Map(rows.map((x) => [x.event_id, x])); mt.note = ""; })
    .catch(() => { mt.locks = new Map(); mt.note = "Couldn't read saved lock-ins just now: planning without them."; })
    .finally(replan);
}
// The search takes a moment: "Planning…" is drawn first
function replan() {
  const mt = state.myTeam;
  mt.result = null;
  renderMyTeam();
  setTimeout(() => {
    try { mt.result = myTeamPlan(); } catch (err) { console.error(err); mt.result = false; }
    renderMyTeam();
  }, 20);
}
function myTeamPlan() {
  const mt = state.myTeam, t = mt.team;
  const prep = FplPlanner.prepare(mt.pred, t);
  if (!prep) return false;
  const lock = mt.locks.get(t.next_event) || null;
  const ftFpl = Math.max(t.free_transfers - t.made.length, 0);   // left after any already made in FPL
  const ft = mt.ft ?? ftFpl;
  let first = null;
  if (lock) {
    // once FPL shows transfers for the week, its squad already has them: the lock only marks the week done
    first = t.made.length ? [] : lock.transfers.map((m) => ({ out: m.out, in: m.in }));
    if (first.length && !FplPlanner.apply(prep.ctx, prep.start, first)) first = [];
  }
  const plan = FplPlanner.plan(prep, { ft, first });
  return { prep, plan, chips: FplPlanner.chipAdvice(prep, plan, t.chips, { locked: !!lock }), lock, ft, ftFpl };
}

function renderMyTeam() {
  const body = $("#myteam-body");
  const mt = state.myTeam;
  const note = (text) => `<div class="stats-card"><div class="stats-note">${text}</div></div>`;
  if (!mt || mt.team === undefined) { body.innerHTML = note("Loading…"); return; }
  if (loadFailed("fpl_team", "fpl_predictions")) { body.innerHTML = loadError("the team"); return; }
  if (!mt.team) { body.innerHTML = note("The team appears after the next FPL update."); return; }
  if (!mt.pred) { body.innerHTML = note("No predictions for the coming gameweeks yet."); return; }
  const t = mt.team, d = mt.pred, r = mt.result;
  const money = (tenths) => `£${(tenths / 10).toFixed(1)}m`;
  const passed = new Date(t.next_deadline) <= new Date();
  const ftNow = r ? r.ft : mt.ft ?? Math.max(t.free_transfers - t.made.length, 0);
  const head = `<div class="stats-card mt-head">
      <div class="mt-title"><b>${escapeHtml(t.name)}</b>
        <span>GW${t.next_event} deadline ${escapeHtml(fmtDay(t.next_deadline))}, ${escapeHtml(fmtTime(t.next_deadline))}${passed ? " · passed: the page catches up at the next FPL update" : ""}</span></div>
      <div class="mt-stats">
        <div><span class="stats-label">Bank</span><b>${money(t.bank)}</b></div>
        <div><label class="stats-label" for="mt-ft" title="Worked out from your FPL history. If FPL shows a different number, change it here.">Free transfers</label>
          <select id="mt-ft" class="mt-select">${[0, 1, 2, 3, 4, 5].map((n) => `<option value="${n}"${n === ftNow ? " selected" : ""}>${n}</option>`).join("")}</select></div>
        <div><span class="stats-label">Points</span><b>${t.overall_points ?? "–"}</b></div>
        <div><span class="stats-label">Overall rank</span><b>${t.overall_rank ? t.overall_rank.toLocaleString("en-GB") : "–"}</b></div>
      </div></div>`;
  if (r === null) { body.innerHTML = head + note("Planning…"); return; }
  if (!r) { body.innerHTML = head + note("Couldn't plan: the predictions don't cover the next gameweek yet."); return; }

  const ctx = r.prep.ctx, P = (id) => ctx.players.get(id);
  const nm = (p) => escapeHtml(p.fpl ? p.name : shortName(p.name));
  const code = (id) => d.teams[id]?.[1] || "";
  const fix = (p, k) => p.fixtures[k].length ? p.fixtures[k].map((f) => f.home ? code(f.opponent) : code(f.opponent).toLowerCase()).join(" ") : "–";
  const tag = (p) => {
    const s = p.status && p.status !== "a" ? (p.status === "d" ? `${p.chance ?? 50}%` : FPL_STATUS[p.status] || "Doubtful") : p.missing ? "No prediction" : "";
    return s ? ` <span class="bet-tag warn">${escapeHtml(s)}</span>` : "";
  };
  const before = (k) => k === 0 ? r.prep.start : r.plan.weeks[k - 1];
  const moveLine = (m, k) => {
    const o = P(m.out), i = P(m.in), gain = FplPlanner.moveGain(r.prep, before(k), m, k);
    return `<div class="mt-move"><span><span class="mt-nm">${nm(o)}</span> <small>${FPL_POS[o.pos]} · sell ${money(before(k).sell[m.out])}</small></span>
      <span class="mt-arrow" aria-label="for">→</span>
      <span><span class="mt-nm">${nm(i)}</span> <small>${escapeHtml(code(i.team))} · ${money(i.price)}</small>${tag(i)}</span>
      ${gain != null ? `<b class="mt-gain" title="Expected points gained over the plan's weeks, this transfer alone">${gain >= 0 ? "+" : "−"}${Math.abs(gain).toFixed(1)}</b>` : ""}</div>`;
  };

  // ---- this week
  const w0 = r.plan.weeks[0], H = r.plan.weeks.length;
  const made = t.made.length ? `<div class="stats-note">Already made in FPL: ${t.made.map((m) => `${escapeHtml(m.out_name)} → ${escapeHtml(m.in_name)}`).join(", ")}.</div>` : "";
  const moves = w0.moves.length ? w0.moves.map((m) => moveLine(m, 0)).join("")
    : `<p class="fpl-text">${r.lock ? "No more transfers this week." : `Roll the transfer: nothing gains enough over the next ${H} gameweeks. You'll have ${Math.min(FplPlanner.MAX_FT, ftNow + 1)} free next week.`}</p>`;
  let lock;
  if (r.lock) {
    lock = `<div class="mt-locked"><span>✓ Locked in ${escapeHtml(fmtDay(r.lock.locked_at))}, ${escapeHtml(fmtTime(r.lock.locked_at))}</span>
      ${SUPABASE.key && !passed ? `${storedText("fplKey") ? "" : `<input type="password" id="mt-key" class="table-search" placeholder="Passphrase" aria-label="Passphrase" autocomplete="current-password" value="${escapeHtml(mt.key)}">`}
        <button type="button" class="filter-chip" id="mt-unlock"${mt.busy ? " disabled" : ""}>Undo</button>` : ""}</div>`;
  } else if (!SUPABASE.key || passed) {
    lock = "";
  } else {
    lock = `<div class="mt-lock">
      <input type="password" id="mt-key" class="table-search" placeholder="Passphrase" aria-label="Passphrase" autocomplete="current-password" value="${escapeHtml(mt.key)}">
      <button type="button" class="mt-btn" id="mt-lock"${mt.busy ? " disabled" : ""}>${w0.moves.length ? "I've made these transfers" : "Lock in: no transfers"}</button></div>
      <div class="stats-note">Made different ones? Lock in anyway: the next FPL update (07:00, 13:00 and 19:00 UTC) reads what you actually did.</div>`;
  }
  const week = `<div class="stats-card">
      <div class="stats-label">GW${w0.gw} transfers${r.lock ? " · locked in" : ""}</div>
      ${made}${moves}
      ${w0.hits ? `<div class="stats-note mt-warn">Costs a ${w0.hits}-point hit: worth it over the ${H} gameweeks.</div>` : ""}
      <div class="stats-note">Bank after: ${money(w0.bank)}.</div>
      ${lock}${mt.msg ? `<div class="stats-note mt-warn" role="alert">${escapeHtml(mt.msg)}</div>` : ""}${mt.note ? `<div class="stats-note">${escapeHtml(mt.note)}</div>` : ""}
    </div>`;

  // ---- line-up for the coming gameweek
  const lu = w0.lineup;
  const player = (p) => `<div class="mt-player"><span class="mt-nm">${nm(p)}${p.id === lu.captain ? ' <b class="mt-c" title="Captain">C</b>' : p.id === lu.vice ? ' <b class="mt-c v" title="Vice-captain">V</b>' : ""}</span>
    <small>${escapeHtml(fix(p, 0))} · ${p.xp[0].toFixed(1)}</small>${tag(p)}</div>`;
  const row = (pos) => `<div class="mt-row">${lu.xi.map(P).filter((p) => p.pos === pos).map(player).join("")}</div>`;
  const pitch = `<div class="stats-card">
      <div class="stats-label">GW${w0.gw} line-up · ${lu.points.toFixed(1)} expected points</div>
      <div class="mt-pitch">${["G", "D", "M", "F"].map(row).join("")}</div>
      <div class="stats-label mt-sub">Bench, in order</div>
      <div class="mt-row mt-bench">${lu.bench.map(P).map(player).join("")}</div>
    </div>`;

  // ---- the plan
  const planRows = r.plan.weeks.map((w, k) => `<tr><td>GW${w.gw}${k === 0 && r.lock ? " ✓" : ""}</td><td>${w.ft}</td>
      <td class="mt-plan-moves">${w.moves.length ? w.moves.map((m) => `${nm(P(m.out))} → ${nm(P(m.in))}`).join("<br>") : '<span class="dim-text">Roll</span>'}</td>
      <td>${w.hits ? `−${w.hits}` : ""}</td><td>${nm(P(w.lineup.captain))}</td><td><b>${w.points.toFixed(1)}</b></td></tr>`).join("");
  const plan = `<div class="stats-card">
      <div class="stats-label">Plan · next ${H} gameweeks</div>
      <div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table mt-plan"><thead><tr><th>GW</th><th title="Free transfers that week">Free</th><th>Transfers</th><th>Hit</th><th>Captain</th><th>Pts</th></tr></thead>
        <tbody>${planRows}</tbody></table></div>
      <div class="stats-note">${r.plan.total.toFixed(1)} expected points over GW${r.plan.weeks[0].gw}–${r.plan.weeks[H - 1].gw},
        ${(r.plan.total - r.plan.hold).toFixed(1)} more than making no transfers. Later weeks are a sketch: each week the plan is worked out again with the latest predictions.</div>
    </div>`;

  // ---- chips
  const last = ctx.weeks[ctx.weeks.length - 1].id;
  const chipRows = r.chips.map((a) => {
    const name = `<b>${CHIP_NAMES[a.name]}</b>`;
    if (a.played != null && !a.options) return `<div class="mt-chip"><div>${name}<span class="fpl-badge">PLAYED GW${a.played}</span></div></div>`;
    if (!a.options) return "";
    if (a.verdict === "later") return `<div class="mt-chip"><div>${name}<span class="fpl-badge">FROM GW${a.window[0]}</span></div>
      <div class="stats-note">Can be played GW${a.window[0]}–${a.window[1]}: after the gameweeks predicted so far.</div></div>`;
    const b = a.best;
    const badge = a.verdict === "play" ? `<span class="fpl-badge pass">PLAY GW${b.gw}</span>`
      : a.verdict === "last" ? `<span class="fpl-badge pass">LAST CHANCE: GW${b.gw}</span>` : `<span class="fpl-badge">HOLD</span>`;
    const why = a.verdict === "play" ? `+${b.gain.toFixed(1)} expected points ${CHIP_GAIN[a.name]}.`
      : a.verdict === "last" ? `+${b.gain.toFixed(1)} expected points ${CHIP_GAIN[a.name]}: its window closes after GW${a.window[1]}, so play it in its best week left.`
      : b ? `Best week so far is GW${b.gw} at +${b.gain.toFixed(1)} ${CHIP_GAIN[a.name]}; it's worth playing from about +${FplPlanner.CHIP_PLAY[a.name]}, usually a double gameweek. Play by GW${a.window[1]}.`
      : `No week left for it in the predictions. Play by GW${a.window[1]}.`;
    const others = a.options.filter((o) => o !== b).slice(0, 4).map((o) => `GW${o.gw} +${o.gain.toFixed(1)}`).join(" · ");
    const squad = b?.squad && a.verdict !== "hold" ? (() => {
      const from = before(b.k).squad, out = from.filter((id) => !b.squad.includes(id)), inn = b.squad.filter((id) => !from.includes(id));
      return out.length ? `<details class="mt-details"><summary>The ${CHIP_NAMES[a.name]} squad's changes</summary>
        ${out.map((id, i) => `<div class="mt-move"><span class="mt-nm">${nm(P(id))}</span><span class="mt-arrow">→</span><span class="mt-nm">${nm(P(inn[i]))}</span></div>`).join("")}</details>` : "";
    })() : "";
    return `<div class="mt-chip"><div>${name}${badge}</div><div class="stats-note">${why}${others ? ` Other weeks: ${others}.` : ""}</div>${squad}</div>`;
  }).join("");
  const chips = `<div class="stats-card">
      <div class="stats-label">Chips</div>${chipRows}
      <div class="stats-note">Predictions reach GW${last}, so the advice moves as later gameweeks come into view, and double gameweeks only show once FPL schedules them. One chip a gameweek.</div>
    </div>`;

  // ---- squad by week
  const order = { G: 0, D: 1, M: 2, F: 3 };
  const squad = [...r.prep.start.squad].map(P).sort((a, b) => order[a.pos] - order[b.pos] || b.xp[0] - a.xp[0]);
  const weeksHead = ctx.weeks.slice(0, H).map((g) => `<th>GW${g.id}</th>`).join("");
  const squadRows = squad.map((p) => `<tr><td class="mt-nm-cell"><span class="mt-nm">${nm(p)}</span>${tag(p)}</td><td>${FPL_POS[p.pos]}</td>
      <td title="Selling price ${money(r.prep.start.sell[p.id])}">${money(p.price)}</td>
      ${ctx.weeks.slice(0, H).map((_, k) => `<td class="fpl-gw${p.fixtures[k].length > 1 ? " double" : ""}">${p.fixtures[k].length ? p.xp[k].toFixed(1) : "–"}<span>${escapeHtml(fix(p, k))}</span></td>`).join("")}</tr>`).join("");
  const table = `<div class="stats-card">
      <div class="stats-label">Your squad · expected points</div>
      <div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table mt-squad"><thead><tr><th>Player</th><th>Pos</th><th>Price</th>${weeksHead}</tr></thead><tbody>${squadRows}</tbody></table></div>
    </div>`;

  body.innerHTML = head + week + pitch + plan + chips + table + `<div class="stats-note mt-foot">
      Expected points are ${escapeHtml(d.model)}'s, from the FPL tab. The plan searches the next ${H} gameweeks for the transfers that add the most:
      each week it rolls the free transfer or makes one, two or three moves, and a move beyond the free ones costs 4 points.
      A squad is scored by its best line-up with the captain doubled, plus a little for the bench; each later week counts 10% less than the one before,
      and a free transfer still banked at the end is worth 1.5 points. Selling prices keep half of any rise, as FPL does.
      Squad, bank, free transfers and chips come from FPL (updated at 07:00, 13:00 and 19:00 UTC). A guide, not advice.</div>`;
}
async function lockMyTransfers(undo) {
  const mt = state.myTeam, r = mt.result, t = mt.team;
  if (!r || mt.busy) return;
  const P = (id) => r.prep.ctx.players.get(id);
  const transfers = r.plan.weeks[0].moves.map((m) => ({ out: m.out, in: m.in, out_name: P(m.out).name, in_name: P(m.in).name,
    sell: r.prep.start.sell[m.out], buy: P(m.in).price }));
  mt.busy = true; mt.msg = "";
  renderMyTeam();
  try {
    const args = { p_entry: t.entry, p_season: t.season, p_event: t.next_event, p_key: mt.key };
    const res = await supabase(`rpc/${undo ? "unlock" : "lock"}_fpl_transfers`, undo ? args : { ...args, p_transfers: transfers });
    if (!res.ok) { mt.msg = res.error; storeText("fplKey", ""); }
    else {
      storeText("fplKey", mt.key);
      if (undo) mt.locks.delete(t.next_event);
      else mt.locks.set(t.next_event, { event_id: t.next_event, transfers, locked_at: res.locked_at });
    }
  } catch { mt.msg = "Couldn't reach the database: nothing was saved."; }
  mt.busy = false;
  if (mt.msg) renderMyTeam(); else replan();
}
$("#myteam-body").addEventListener("click", (e) => {
  if (e.target.id === "mt-lock") lockMyTransfers(false);
  if (e.target.id === "mt-unlock") lockMyTransfers(true);
});
$("#myteam-body").addEventListener("change", (e) => {
  if (e.target.id !== "mt-ft") return;
  const mt = state.myTeam;
  mt.ft = +e.target.value === mt.result?.ftFpl ? null : +e.target.value;
  replan();
});
$("#myteam-body").addEventListener("input", (e) => { if (e.target.id === "mt-key") state.myTeam.key = e.target.value; });

// ------------------------------------------------------------------ EFL Fantasy
// Expected Fantasy EFL points for Championship, League One and League Two players and clubs
// (efl_predictions.json, from thecornerfc/efl_fantasy.py; loaded when the tab first opens). Nothing
// comes from the Fantasy EFL site: positions are guessed from match data (efl_positions.json corrects them).
const EFL_SHOWN = 30;
const EFL_FORMATIONS = [[2, 2, 2], [2, 3, 1], [3, 2, 1]];      // DEF-MID-FWD behind one goalkeeper
const EFL_PARTS = { appearance: "Minutes", goal: "Goals", hat_trick: "Hat-trick", assist: "Assists", penalty_miss: "Penalty misses",
  clean_sheet: "Clean sheet", goals_conceded: "Goals conceded", save: "Saves", penalty_save: "Penalty saves", card: "Cards",
  tackle: "Tackles", block: "Blocks", clearance: "Clearances", interception: "Interceptions", key_pass: "Key passes",
  shot_on_target: "Shots on target" };
const EFL_CLUB_PARTS = { win: "Win", draw: "Draw", away_win: "Away win", clean_sheet: "Clean sheet", goals_2: "2+ goals", goals_4: "4+ goals" };
const EFL_LEAGUE_SHORT = { 40: "Champ", 41: "L1", 42: "L2" };
function loadEfl() {
  if (state.efl !== undefined) return;
  state.efl = null;
  renderEfl();
  Promise.all([getJsonOrNull("data/efl_predictions.json"), loadPlayers()]).then(([d]) => { state.efl = d || false; renderEfl(); });
}
function eflData() {
  const d = state.efl;
  if (d.rows) return d;
  const obj = (fields, r) => Object.fromEntries(fields.map((k, j) => [k, r[j]]));
  d.rows = d.players.map((r, i) => {
    const p = obj(d.fields, r);
    p.name = decodeEntities(p.name);
    p.league = d.teams[p.team]?.[2];
    p.cells = d.cells[i].map((c) => obj(d.cell_fields, c));
    return p;
  });
  d.clubRows = Object.entries(d.clubs).map(([team, cs]) => ({ team: +team, league: d.teams[team]?.[2], cells: cs.map((c) => obj(d.club_fields, c)) }));
  return d;
}
// The best 7 + 2 for one gameweek: for each formation, players by expected points with at most two
// from a club; the captain's points count twice. Greedy, so close to the best rather than exact.
function eflBestTeam(rows, clubs, gw) {
  const pts = (cells) => cells.filter((c) => c.gw === gw).reduce((a, c) => a + c.xp, 0);
  const pool = rows.map((p) => ({ p, xp: pts(p.cells) })).filter((r) => r.xp > 0).sort((a, b) => b.xp - a.xp);
  let best = null;
  for (const [nd, nm, nf] of EFL_FORMATIONS) {
    const need = { G: 1, D: nd, M: nm, F: nf }, per = {}, xi = [];
    for (const r of pool) {
      if (!need[r.p.position] || (per[r.p.team] || 0) >= 2) continue;
      need[r.p.position]--; per[r.p.team] = (per[r.p.team] || 0) + 1; xi.push(r);
      if (xi.length === 7) break;
    }
    if (xi.length < 7) continue;
    const total = xi.reduce((a, r) => a + r.xp, 0) + xi[0].xp;
    if (!best || total > best.total) best = { xi, total, formation: `1-${nd}-${nm}-${nf}` };
  }
  const picks = clubs.map((c) => ({ c, xp: pts(c.cells) })).filter((r) => r.xp > 0).sort((a, b) => b.xp - a.xp).slice(0, 2);
  if (best) best.clubs = picks;
  return best;
}
function renderEfl() {
  const body = $("#efl-body");
  const note = (text) => `<div class="stats-card"><div class="stats-note">${text}</div></div>`;
  if (state.efl == null) { body.innerHTML = note("Loading…"); return; }
  if (!state.efl || !state.efl.players.length) { body.innerHTML = loadFailed("efl_predictions") ? loadError("the predictions") : note("No upcoming EFL gameweeks yet."); return; }
  const d = eflData();
  const v = state.eflView ||= { pos: "all", league: "all", q: "", sort: "xp", all: false, mode: "gw", gw: 0, open: null, clubsAll: false };
  const gws = d.gameweeks;
  v.gw = Math.max(0, Math.min(v.gw, gws.length - 1));
  const n = v.mode === "gw" ? 1 : Math.min(+v.mode, gws.length);
  const span = v.mode === "gw" ? [gws[v.gw].id] : gws.slice(0, n).map((g) => g.id);
  const team = (id) => d.teams[id]?.[0] || teamName(id), code = (id) => d.teams[id]?.[1] || team(id).slice(0, 3).toUpperCase();
  const day = (iso) => new Date(iso).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  const range = (g) => `${day(g.start + "T12:00:00")} – ${day(g.end + "T12:00:00")}`;
  const opp = (c) => c.home ? code(c.opponent) : code(c.opponent).toLowerCase();
  const vs = (cells) => cells.length ? cells.map((c) => `v ${escapeHtml(team(c.opponent))} ${c.home ? "H" : "A"}`).join(" · ") : "No match (blank)";
  const pick = (cells) => cells.filter((c) => span.includes(c.gw));
  const q = v.q.trim().toLowerCase();
  const inLeague = (lg) => v.league === "all" || String(lg) === v.league;
  const nameOf = (p) => playerById(p.player) ? playerLink(p.player, shortName(p.name)) : escapeHtml(shortName(p.name));
  const tag = (p) => p.availability ? ` <span class="bet-tag warn" title="On the injury list">${p.availability === "Missing Fixture" ? "Out" : "Doubtful"}</span>` : "";

  // ---- suggested team for the gameweek shown (the first one in the multi-gameweek views)
  const g0 = v.mode === "gw" ? gws[v.gw] : gws[0];
  const best = eflBestTeam(d.rows.filter((p) => inLeague(p.league)), d.clubRows.filter((c) => inLeague(c.league)), g0.id);
  let suggest = "";
  if (best) {
    const cap = best.xi[0].p.player, vice = best.xi[1].p.player;
    const card = (r) => `<div class="mt-player"><span class="mt-nm">${nameOf(r.p)}${r.p.player === cap ? ' <b class="mt-c" title="Captain">C</b>' : r.p.player === vice ? ' <b class="mt-c v" title="Vice-captain">V</b>' : ""}</span>
      <small>${escapeHtml(code(r.p.team))} · ${r.xp.toFixed(1)}</small>${tag(r.p)}</div>`;
    const row = (pos) => `<div class="mt-row">${best.xi.filter((r) => r.p.position === pos).map(card).join("")}</div>`;
    const clubs = best.clubs.map((r) => `<div class="mt-player"><span class="mt-nm">${escapeHtml(team(r.c.team))}</span>
      <small>${r.c.cells.filter((c) => c.gw === g0.id).map((c) => `v ${escapeHtml(code(c.opponent))} ${c.home ? "H" : "A"}`).join(" · ")} · ${r.xp.toFixed(1)}</small></div>`).join("");
    const total = best.total + best.clubs.reduce((a, r) => a + r.xp, 0);
    suggest = `<div class="stats-card">
      <div class="stats-label">Suggested team · GW${g0.id} (${range(g0)}) · ${total.toFixed(1)} expected points</div>
      <div class="mt-pitch">${["G", "D", "M", "F"].map(row).join("")}</div>
      <div class="stats-label mt-sub">Clubs</div>
      <div class="mt-row mt-bench">${clubs}</div>
      <div class="stats-note">${best.formation}, at most two players from a club, captain (C) on the most expected points.
        ${v.league === "all" ? "" : `Only ${escapeHtml(d.leagues[v.league])}. `}It doesn't know how many of your five picks of each club you've used.</div>
    </div>`;
  }

  // ---- players
  const rows = d.rows.filter((p) => inLeague(p.league) && (v.pos === "all" || p.position === v.pos)
      && (!q || p.name.toLowerCase().includes(q) || team(p.team).toLowerCase().includes(q)))
    .map((p) => {
      const cells = pick(p.cells), sum = (k) => cells.reduce((a, c) => a + c[k], 0);
      return { p, cells, xp: sum("xp"), minutes: sum("minutes"), goals: sum("goals"), assists: sum("assists") };
    }).sort((a, b) => b[v.sort] - a[v.sort] || b.xp - a.xp);
  const list = v.all ? rows : rows.slice(0, EFL_SHOWN);
  const who = (r) => `<td class="fpl-player"><div class="fpl-who"><span class="fpl-face">${personChip(r.p.name)}
      ${clubCrest(r.p.team, "club-logo", `data-club="${r.p.team}" title="${escapeHtml(team(r.p.team))}"`, team(r.p.team))}</span>
      <div class="fpl-name"><div class="fpl-line"><span class="fpl-nm" title="${escapeHtml(r.p.name)}">${nameOf(r.p)}</span>
        <span class="fpl-meta"><span title="${FPL_POS[r.p.position]}${r.p.corrected ? "" : ": guessed from match data"}">${escapeHtml(r.p.position)}${r.p.corrected ? "" : "*"}</span> · ${EFL_LEAGUE_SHORT[r.p.league] || ""}</span>${tag(r.p)}</div>
      <div class="fpl-match">${v.mode === "gw" ? vs(r.cells) : escapeHtml(team(r.p.team))}</div></div></div></td>`;
  const pts = (r) => `<button type="button" class="fpl-pts" data-efl-break="${r.p.player}" aria-expanded="${v.open === r.p.player}" title="Where the points come from"><b>${r.xp.toFixed(1)}</b></button>`;
  const line = (label, figure, x) => `<div class="fpl-part"><span>${label}</span><span>${figure ?? ""}</span>
      <b class="${x < 0 ? "neg" : ""}">${x < 0 ? "−" : ""}${Math.abs(x).toFixed(2)}</b></div>`;
  const breakdown = (r, cols) => {
    if (v.open !== r.p.player) return "";
    const one = r.cells.length === 1 ? r.cells[0] : null;
    const stat = { appearance: r.minutes, goal: r.goals.toFixed(2), assist: r.assists.toFixed(2),
      clean_sheet: one ? `${Math.round(one.p_clean_sheet * 100)}%` : "" };
    const parts = d.part_fields.map((k, j) => [k, r.cells.reduce((a, c) => a + (c.parts[j] || 0), 0)]).filter(([, x]) => Math.abs(x) >= 0.005);
    return `<tr class="fpl-break"><td class="fpl-parts-cell" colspan="${cols}"><div class="fpl-parts">
      ${parts.map(([k, x]) => line(EFL_PARTS[k] || k, stat[k], x)).join("")}</div></td></tr>`;
  };
  const sortTh = (k, label, title = "") => `<th${title ? ` title="${title}"` : ""}><button type="button" class="fpl-sort${v.sort === k ? " on" : ""}" data-efl-sort="${k}" aria-pressed="${v.sort === k}"${title ? ` aria-label="${title}"` : ""}>${label}</button></th>`;
  const gwCell = (cs) => !cs.length ? `<td class="fpl-gw dim-text">–</td>`
    : `<td class="fpl-gw${cs.length > 1 ? " double" : ""}">${cs.reduce((a, c) => a + c.xp, 0).toFixed(1)}<span>${cs.map(opp).join(" ")}</span></td>`;
  let head, tbody, cols;
  if (v.mode === "gw") {
    cols = 6;
    head = `<th>#</th><th>Player</th>${sortTh("xp", "Pts")}${sortTh("minutes", "Mins")}${sortTh("goals", "G", "Expected goals")}${sortTh("assists", "A", "Expected assists")}`;
    tbody = list.map((r, i) => `<tr><td>${i + 1}</td>${who(r)}<td>${pts(r)}</td><td>${r.minutes}</td>
      <td>${r.goals.toFixed(2)}</td><td>${r.assists.toFixed(2)}</td></tr>${breakdown(r, cols)}`).join("");
  } else {
    cols = 3 + span.length;
    head = `<th>#</th><th>Player</th>${sortTh("xp", "Total")}` + span.map((id) => {
      const g = gws.find((x) => x.id === id);
      return `<th title="${range(g)}">GW${id}</th>`;
    }).join("");
    tbody = list.map((r, i) => `<tr><td>${i + 1}</td>${who(r)}<td>${pts(r)}</td>${span.map((id) => gwCell(r.cells.filter((c) => c.gw === id))).join("")}</tr>${breakdown(r, cols)}`).join("");
  }
  const chip = (attr, k, label, on) => `<button type="button" class="filter-chip" data-${attr}="${k}" aria-pressed="${on}">${label}</button>`;
  const modes = [["gw", "Gameweek"], ["3", "Next 3"], ["6", "Next 6"]].map(([k, label]) => chip("efl-mode", k, label, v.mode === k)).join("");
  const pager = v.mode !== "gw" ? `<span class="fpl-span">GW${span[0]}–${span[span.length - 1]}</span>`
    : `<span class="fpl-pager"><button type="button" class="filter-chip" data-efl-step="-1" aria-label="Previous gameweek" ${v.gw === 0 ? "disabled" : ""}>◀</button>
       <span class="fpl-span">GW${gws[v.gw].id} · ${range(gws[v.gw])}</span>
       <button type="button" class="filter-chip" data-efl-step="1" aria-label="Next gameweek" ${v.gw === gws.length - 1 ? "disabled" : ""}>▶</button></span>`;
  const leagues = [["all", "All leagues"], ...Object.entries(d.leagues)].map(([k, label]) => chip("efl-league", k, escapeHtml(label), v.league === k)).join("");
  const posChips = [["all", "All"], ["G", "GK"], ["D", "DEF"], ["M", "MID"], ["F", "FWD"]].map(([k, label]) => chip("efl-pos", k, label, v.pos === k)).join("");
  const players = `<div class="stats-card">
    <div class="stats-label">Predicted points</div>
    <div class="fpl-filters">${posChips}
      <input type="search" class="table-search fpl-search" id="efl-q" placeholder="Search players or clubs" aria-label="Search players or clubs" value="${escapeHtml(v.q)}"></div>
    <div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table fpl-table${v.mode === "gw" ? "" : " multi"}">
      <thead><tr>${head}</tr></thead>
      <tbody>${tbody || `<tr><td colspan="${cols}">No players match.</td></tr>`}</tbody></table></div>
    ${rows.length > EFL_SHOWN ? `<button type="button" class="show-all" id="efl-more">${v.all ? "Show fewer" : `Show all ${rows.length}`}</button>` : ""}
    </div>`;

  // ---- club picks
  const clubs = d.clubRows.filter((c) => inLeague(c.league) && (!q || team(c.team).toLowerCase().includes(q))).map((c) => {
    const cells = pick(c.cells);
    return { c, cells, xp: cells.reduce((a, x) => a + x.xp, 0) };
  }).filter((r) => r.cells.length).sort((a, b) => b.xp - a.xp);
  const clubList = v.clubsAll ? clubs : clubs.slice(0, 12);
  const clubHead = v.mode === "gw" ? `<th>#</th><th>Club</th><th>Pts</th><th title="Chance of winning">Win</th><th title="Chance of a clean sheet">CS</th>`
    : `<th>#</th><th>Club</th><th>Total</th>${span.map((id) => `<th>GW${id}</th>`).join("")}`;
  const clubRow = (r, i) => {
    const name = `<td class="fpl-player"><div class="fpl-who">${clubCrest(r.c.team, "efl-club-logo")}
      <div class="fpl-name"><div class="fpl-line"><span class="fpl-nm">${escapeHtml(team(r.c.team))}</span><span class="fpl-meta">${EFL_LEAGUE_SHORT[r.c.league] || ""}</span></div>
      ${v.mode === "gw" ? `<div class="fpl-match">${vs(r.cells)}</div>` : ""}</div></div></td>`;
    if (v.mode !== "gw") return `<tr><td>${i + 1}</td>${name}<td><b>${r.xp.toFixed(1)}</b></td>${span.map((id) => gwCell(r.cells.filter((c) => c.gw === id))).join("")}</tr>`;
    const pct = (k) => r.cells.map((c) => `${Math.round(c[k] * 100)}%`).join(" · ");
    const title = d.club_part_fields.map((k, j) => `${EFL_CLUB_PARTS[k]} ${r.cells.reduce((a, c) => a + c.parts[j], 0).toFixed(2)}`).join(", ");
    return `<tr><td>${i + 1}</td>${name}<td title="${title}"><b>${r.xp.toFixed(1)}</b></td><td>${pct("p_win")}</td><td>${pct("p_clean_sheet")}</td></tr>`;
  };
  const clubCard = `<div class="stats-card">
    <div class="stats-label">Club picks</div>
    <div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table fpl-table${v.mode === "gw" ? "" : " multi"}">
      <thead><tr>${clubHead}</tr></thead><tbody>${clubList.map(clubRow).join("") || `<tr><td colspan="5">No clubs match.</td></tr>`}</tbody></table></div>
    ${clubs.length > 12 ? `<button type="button" class="show-all" id="efl-clubs-more">${v.clubsAll ? "Show fewer" : `Show all ${clubs.length}`}</button>` : ""}
    </div>`;

  const notes = `<div class="stats-card"><div class="stats-note">
    Points use Fantasy EFL's scoring. Everyone: 1 for playing, 2 for 60 minutes, 3 an assist, 5 a hat-trick, −3 a missed penalty, −1 a yellow and −3 a red.
    Goals: 10 goalkeeper, 7 defender, 6 midfielder, 5 forward. Goalkeepers and defenders: 5 a clean sheet (60+ minutes), −1 per 2 conceded; goalkeepers 2 per 3 saves and 5 a penalty save.
    Defenders: 1 per 2 tackles, per 2 blocks and per 4 clearances. Midfielders: 2 an interception. Midfielders and forwards: 1 per 2 key passes and 1 a shot on target.
    Clubs: 5 a win (2 more away), 3 a draw, 2 a clean sheet, 2 for 2+ goals and 2 more for 4+.
    <br><br>Minutes, goals, assists, penalties, clean sheets, saves and cards come from the same model as the FPL tab, run on each division's own matches and our match predictions.
    Tackles, blocks, interceptions, key passes and shots on target are each player's own rates over the last year, pulled toward his role's when he's played little.
    Our match data has no clearances, so defenders get a typical rate for their role (centre-backs 5 a match, full-backs 2.2): a rough guess. Own goals aren't included.
    <br><br>Positions marked * are guessed from match data and may not match Fantasy EFL's; corrected ones have no mark.
    Gameweeks run Thursday to Wednesday, numbered from the season's first week, so check the numbers against the game. Predictions further ahead assume today's form and fitness.
    This is ${escapeHtml(d.model)}, not yet tested against real Fantasy EFL scores: a guide, not a pick list. Click a player's points to see where they come from.</div></div>`;

  body.innerHTML = `<div class="fpl-filters">${modes}${pager}</div><div class="fpl-filters">${leagues}</div>${suggest}${players}${clubCard}${notes}`;
  body.querySelectorAll(".fpl-table.multi").forEach((t) => t.style.setProperty("--fz2", `${t.tHead.rows[0].cells[0].getBoundingClientRect().width}px`));
}
$("#efl-body").addEventListener("click", (e) => {
  const t = (sel) => e.target.closest(sel);
  const pos = t("[data-efl-pos]"), league = t("[data-efl-league]"), sort = t("[data-efl-sort]"), mode = t("[data-efl-mode]");
  const step = t("[data-efl-step]"), brk = t("[data-efl-break]");
  const more = e.target.id === "efl-more", clubsMore = e.target.id === "efl-clubs-more";
  if (!pos && !league && !sort && !mode && !step && !brk && !more && !clubsMore) return;
  const v = state.eflView;
  if (brk) v.open = v.open === +brk.dataset.eflBreak ? null : +brk.dataset.eflBreak;
  if (pos) { v.pos = pos.dataset.eflPos; v.all = false; }
  if (league) { v.league = league.dataset.eflLeague; v.all = false; v.clubsAll = false; }
  if (sort) v.sort = sort.dataset.eflSort;
  if (mode) { v.mode = mode.dataset.eflMode; v.all = false; if (v.mode !== "gw") v.sort = "xp"; }
  if (step) v.gw += +step.dataset.eflStep;
  if (more) v.all = !v.all;
  if (clubsMore) v.clubsAll = !v.clubsAll;
  renderEfl();
});
$("#efl-body").addEventListener("input", (e) => {
  if (e.target.id !== "efl-q") return;
  state.eflView.q = e.target.value;
  state.eflView.all = false;
  const at = e.target.selectionStart;
  renderEfl();
  const box = $("#efl-q"); box.focus(); box.setSelectionRange(at, at);
});

// ------------------------------------------------------------------ wiring
// The tabs drawn from the start-up files: each is drawn the first time it's opened
const TAB_DRAW = { matches: renderMatches, table: renderTable, stats: renderStats, bets: renderBets, tips: renderTips, fpl: renderFpl };
function showTab(tab) {
  // on screen first, so a first draw measures its rows; and drawn before state.tab changes, so a
  // first draw of the table doesn't put its filters in the address
  document.body.dataset.tab = tab;
  document.querySelectorAll(".panel").forEach((p) => p.dataset.active = String(p.dataset.tab === tab));
  if (TAB_DRAW[tab] && !state.drawn.has(tab)) TAB_DRAW[tab]();
  state.tab = tab;
  if (tab === "fpl") loadFplPredictions();
  if (tab === "myteam") loadMyTeam();
  if (tab === "efl") loadEfl();
  if (tab === "leagues") renderLeagues();
  if (tab === "nations") { loadNations(); if (state.players === undefined) loadPlayers().then(renderNations); renderNations(); }
  if (tab === "lineups") { loadLineupRecord(); renderLineupRecord(); }
  syncMenu();
}
function syncMenu() {
  let title = "";
  document.querySelectorAll("nav.tabs button").forEach((b) => {
    const on = b.dataset.tab === state.tab && (!b.dataset.view || b.dataset.view === state.tableView);
    b.setAttribute("aria-selected", String(on));
    if (on) title = b.textContent;
  });
  $("#app-title").textContent = title;
  setTitle(title);
}
// Each tab other than the tables has its own address, so a reload (or a shared link) stays on it
const TAB_ROUTES = { leagues: "leagues", nations: "nations", matches: "matches", stats: "stats", lineups: "lineups", tips: "model-vs-market", bets: "simulation", fpl: "fpl", myteam: "my-fpl-team", efl: "efl-fantasy" };
const ROUTE_TABS = Object.fromEntries(Object.entries(TAB_ROUTES).map(([t, r]) => [r, t]));
document.querySelectorAll("nav.tabs button").forEach((btn) => btn.addEventListener("click", () => {
  const to = TAB_ROUTES[btn.dataset.tab] ? `#/${TAB_ROUTES[btn.dataset.tab]}` : location.pathname + location.search;
  if (TAB_ROUTES[btn.dataset.tab] ? location.hash !== to : location.hash.startsWith("#/")) history.pushState(null, "", to);
  const view = btn.dataset.view && btn.dataset.view !== state.tableView ? btn.dataset.view : null;
  if (view) state.drawn.add("table");          // setTableView draws it
  showTab(btn.dataset.tab);
  if (view) setTableView(view);
  else if (btn.dataset.tab === "table") syncTableUrl();
  setMenu(false);
}));
// Phones: the menu slides in from the left behind the menu button
function setMenu(open) {
  document.body.classList.toggle("menu-open", open);
  $("#menu-btn").setAttribute("aria-expanded", String(open));
  $("#menu-backdrop").hidden = !open;
}
$("#menu-btn").addEventListener("click", () => setMenu(!document.body.classList.contains("menu-open")));
$("#menu-backdrop").addEventListener("click", () => setMenu(false));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") setMenu(false); });
function route() {
  const club = location.hash.match(/^#\/club\/(\d+)/);
  const player = location.hash.match(/^#\/player\/(\d+)/);
  const nation = location.hash.match(/^#\/nation\/(.+)/);
  const country = location.hash.match(/^#\/country\/(.+)/);
  const league = location.hash.match(/^#\/league\/(\d+)(?:\/(\w+))?/);
  const tableView = location.hash.match(/^#\/(clubs|players)(?:\?(.*))?$/);
  const tab = ROUTE_TABS[location.hash.match(/^#\/([\w-]+)$/)?.[1]];
  if (!state.data) return;
  if (club || player || nation || country || league || tableView) $("#team-modal").hidden = true;
  if (!league) state.league = null;
  if (club) openClubPage(Number(club[1]));
  else if (player) openPlayerPage(Number(player[1]));
  else if (nation) openNationPage(decodeURIComponent(nation[1]));
  else if (country) openCountryPage(decodeURIComponent(country[1]));
  else if (league) openLeaguePage(Number(league[1]), league[2]);
  else if (tableView) openTableView(tableView[1], tableView[2]);
  else if (tab) { showTab(tab); window.scrollTo(0, 0); }
  else showTab(state.tab || "table");
}
window.addEventListener("hashchange", route);
window.addEventListener("popstate", route);
$("#match-filters").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-filter]");
  if (!btn) return;
  state.matchFilter = btn.dataset.filter;
  const lid = matchSingleLeague();
  if (lid != null && matchRounds(lid).length) return setRound(nextRound(lid));
  // nothing in this filter on the day shown: go to its next day with fixtures (or its last, once it's over)
  const ids = matchLeagueIds();
  const days = [...new Set(matchesTab().filter((m) => !ids || ids.includes(m.league))
    .map((m) => localDateStr(new Date(m.kickoff))))].sort();
  if (days.length && !days.includes(state.date)) {
    state.date = days.find((d) => d > state.date) || days[days.length - 1];
    return renderMatches();
  }
  // as on Clubs: the side menu updates in place, phones rebuild
  if (SIDE_MENU.matches) { syncFilterMenu($("#match-filters"), state.matchFilter); renderMatches(false); } else renderMatches();
});
$("#table-filters").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-filter]");
  if (!btn) return;
  state.tableFilter = btn.dataset.filter;
  // Side menu: update in place; phones rebuild (their rows depend on the selection)
  if (SIDE_MENU.matches) syncFilterMenu($("#table-filters"), state.tableFilter); else renderTableFilters();
  renderTable();
});
SIDE_MENU.addEventListener("change", () => { if (state.rankings) { renderTableFilters(); renderMatchFilters(); renderStatsFilters(); renderLineupFilters(); renderBetFilters(); } });
// Stats and Bets menus: as on Clubs, the side menu updates in place and phones rebuild
for (const [id, key, menu, render] of [["#stats-filters", "statsFilter", renderStatsFilters, renderStats],
                                        ["#lineup-filters", "lineupFilter", renderLineupFilters, renderLineupRecord],
                                        ["#bet-filters", "betFilter", renderBetFilters, renderBets]]) {
  $(id).addEventListener("click", (e) => {
    const btn = e.target.closest("[data-filter]");
    if (!btn) return;
    state[key] = btn.dataset.filter;
    if (SIDE_MENU.matches) syncFilterMenu($(id), state[key]); else menu();
    render();
  });
}
for (const [id, key, attr] of [["#bet-strategy", "betStrategy", "strategy"], ["#bet-market", "betMarket", "market"], ["#bet-view", "betView", "view"]]) {
  $(id).addEventListener("click", (e) => {
    const btn = e.target.closest(`[data-${attr}]`);
    if (!btn) return;
    state[key] = btn.dataset[attr];
    document.querySelectorAll(`${id} [data-${attr}]`).forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
    renderBetFilters();
    renderBets();
  });
}
$("#bets-body").addEventListener("click", (e) => {
  const tr = e.target.closest("[data-league]");
  if (!tr) return;
  state.betFilter = state.betFilter === tr.dataset.league ? "all" : tr.dataset.league;
  renderBetFilters();
  renderBets();
});
$("#lineup-source").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-source]");
  if (!btn || btn.dataset.source === state.lineupSource) return;
  state.lineupSource = btn.dataset.source;
  state.lineupShown = LR_PAGE;
  document.querySelectorAll("#lineup-source [data-source]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
  loadLineupRecord();
  renderLineupFilters();
  renderLineupRecord();
});
$("#lineup-ranges").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-range]");
  if (!btn) return;
  state.lineupRange = btn.dataset.range;
  state.lineupShown = LR_PAGE;
  document.querySelectorAll("#lineup-ranges [data-range]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
  renderLineupFilters();
  renderLineupRecord();
});
// a competition row narrows to it (tap again for all); "Show more" lists the next page
$("#lineup-body").addEventListener("click", (e) => {
  if (e.target.closest("[data-more]")) { state.lineupShown += LR_PAGE; return renderLineupRecord(); }
  const tr = e.target.closest("[data-league]");
  if (!tr || e.target.closest("a")) return;
  state.lineupFilter = state.lineupFilter === tr.dataset.league ? "all" : tr.dataset.league;
  state.lineupShown = LR_PAGE;
  renderLineupFilters();
  renderLineupRecord();
});
$("#stats-ranges").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-range]");
  if (!btn) return;
  state.statsRange = btn.dataset.range;
  document.querySelectorAll("#stats-ranges [data-range]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
  renderStats();
});
const byRound = () => !$("#round-select").hidden;
$("#date-prev").addEventListener("click", () => byRound() ? stepRound(-1) : stepDate(-1));
$("#date-next").addEventListener("click", () => byRound() ? stepRound(1) : stepDate(1));
$("#date-today").addEventListener("click", () => {
  if (byRound()) return setRound(nextRound(matchSingleLeague()));
  state.date = localDateStr(new Date());
  renderMatches();
});
$("#round-select").addEventListener("change", (e) => setRound(e.target.value));
$("#date-input").addEventListener("change", (e) => { if (e.target.value) { state.date = e.target.value; renderMatches(); } });
$("#table-search").addEventListener("input", (e) => { state.tableSearch = e.target.value; renderTable(); });
// ---- Age range (Players view)
function ageBounds() {           // youngest and oldest age in the data, worked out once
  if (!state.ageBoundsCache && state.players) {
    const ages = state.players.list.map((p) => p.age).filter((a) => a != null);
    state.ageBoundsCache = ages.length ? [Math.min(...ages), Math.max(...ages)] : [15, 45];
  }
  return state.ageBoundsCache || [15, 45];
}
function inAgeRange(p) {
  const [lo, hi] = ageBounds();
  const min = state.ageMin ?? lo, max = state.ageMax ?? hi;
  if (min <= lo && max >= hi) return true;           // full range: include players with no age
  return p.age != null && p.age >= min && p.age <= max;
}
function renderAgeFilter() {
  const box = $("#age-filter");
  box.hidden = state.tableView !== "players" || !state.players;
  if (box.hidden) return;
  const [lo, hi] = ageBounds();
  const min = state.ageMin ?? lo, max = state.ageMax ?? hi;
  for (const [id, v] of [["#age-min", min], ["#age-max", max]]) {
    const el = $(id);
    el.min = lo; el.max = hi; el.step = 1; el.value = v;
  }
  $("#age-label").textContent = min <= lo && max >= hi ? "All ages" : min === max ? `${min}` : `${min}–${max}`;
  const pct = (v) => ((v - lo) / (hi - lo || 1)) * 100;
  $("#age-fill").style.left = `${pct(min)}%`;
  $("#age-fill").style.right = `${100 - pct(max)}%`;
}
function onAgeInput(e, done) {
  const [lo, hi] = ageBounds();
  let min = Number($("#age-min").value), max = Number($("#age-max").value);
  if (min > max) { if (e.target.id === "age-min") min = max; else max = min; }   // handles can't cross
  state.ageMin = min <= lo ? null : min;
  state.ageMax = max >= hi ? null : max;
  renderAgeFilter();                   // handle and label move straight away
  if (!state.ageFrame)                 // the table redraws at most once per frame while dragging
    state.ageFrame = requestAnimationFrame(() => { state.ageFrame = 0; renderTable(); });
  if (done) renderTableFilters();      // counts in the menu follow the range (on release)
}
for (const id of ["#age-min", "#age-max"]) {
  $(id).addEventListener("input", (e) => onAgeInput(e, false));
  $(id).addEventListener("change", (e) => onAgeInput(e, true));
}

// Clubs or Players, picked from the menu
function setTableView(view) {
  state.tableView = view;
  // Players: drawn again, filters and all, once players.json is in
  if (view === "players" && state.players === undefined)
    loadPlayers().then(() => { if (state.tableView === "players") setTableView("players"); });
  renderExcludeFilter();
  renderRangeFilter();
  renderAgeFilter();
  renderPosFilter();
  renderWhoFilter();
  syncMenu();
  $("#table-search").placeholder = view === "players" ? "Search players or clubs" : "Search clubs, leagues or countries";
  renderTableFilters();
  renderTable();
}

// "Line-ups" (Matches tab) and "Model detail" (Matches tab and club pages) on a match card, each
// opened by its own button and drawn when first opened; the line-ups sit above the model detail.
// On the Matches tab a tap on the card opens its line-ups, and one card is open at a time
async function setMatchPart(card, part, open) {
  const m = state.data.matches.find((x) => x.id === Number(card.dataset.fixture));
  const btn = card.querySelector(part === "why" ? ".why-toggle" : ".lineup-toggle");
  if (!m || !btn) return;
  if (open && card.closest("#matches-list")) {
    document.querySelectorAll("#matches-list .match-card").forEach((c) => { if (c !== card) closeMatchCard(c); });
  }
  btn.setAttribute("aria-expanded", String(open));
  if (part === "lineups") {
    const existing = card.querySelector(".fixture-lineup-panel");
    if (!open) existing?.remove();
    else if (!existing) {
      const panel = document.createElement("div");
      panel.className = "fixture-lineup-panel";
      card.querySelector(".card-toggles").after(panel);
      renderMatchLineups(m, panel);
    }
    return;
  }
  const why = card.querySelector(".why-detail");
  why.hidden = !open;
  if (open) { await loadExplanations(); why.innerHTML = whyDetailHtml(m); }
}
const togglePart = (btn) => btn.classList.contains("why-toggle") ? "why" : "lineups";
function closeMatchCard(card) {
  for (const b of card.querySelectorAll('.card-toggles [aria-expanded="true"]')) setMatchPart(card, togglePart(b), false);
}
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".why-toggle, .lineup-toggle");
  const card = btn?.closest(".match-card");
  if (card) setMatchPart(card, togglePart(btn), btn.getAttribute("aria-expanded") !== "true");
});
$("#matches-list").addEventListener("click", (e) => {
  if (e.target.closest("a")) return;
  if (e.target.closest(".fixture-lineup-panel, .card-toggles, .why-detail")) return;
  const ratingBadge = e.target.closest(".rating-badge");
  if (ratingBadge) {
    const d = ratingBadge.closest(".match-card")?.querySelector(".rating-detail");
    if (d) d.hidden = !d.hidden;
    return;
  }
  const lineupCard = e.target.closest(".match-card.lineup-card");
  if (lineupCard) {
    setMatchPart(lineupCard, "lineups", !lineupCard.querySelector(".fixture-lineup-panel"));
    return;
  }
  const go = e.target.closest("[data-goto]");
  if (go) { state.date = go.dataset.goto; return renderMatches(); }
  const header = e.target.closest(".comp-group-header");
  if (header) {
    const group = header.parentElement, key = group.dataset.comp, id = /^\d+$/.test(key) ? Number(key) : key;
    state.collapsed.has(id) ? state.collapsed.delete(id) : state.collapsed.add(id);
    group.classList.toggle("collapsed");
    header.querySelector(".comp-group-caret").innerHTML = group.classList.contains("collapsed") ? "&#9656;" : "&#9662;";
    header.setAttribute("aria-expanded", String(!group.classList.contains("collapsed")));
  }
});
// Column explanations: hover a header in the Rankings table
const colTip = Object.assign(document.createElement("div"), { className: "col-tip", hidden: true });
colTip.setAttribute("role", "tooltip");
document.body.appendChild(colTip);
// (not on touch screens: a tap sends mouseover too, and the tip would stay up)
const CAN_HOVER = matchMedia("(hover: hover)");
$("#table-wrap").addEventListener("mouseover", (e) => {
  if (!CAN_HOVER.matches) return;
  const h = e.target.closest("th[data-tip], td.tip-cell");
  if (!h) return;
  const show = () => {
    colTip.textContent = h.dataset.tip || playerCellTip(h.closest("tr").dataset.player, h.dataset.key);
    if (!colTip.textContent) return;
    colTip.hidden = false;
    colTip.cell = h;
    const b = h.getBoundingClientRect(), w = colTip.offsetWidth;
    colTip.style.left = `${Math.max(8, Math.min(b.left + b.width / 2 - w / 2, innerWidth - w - 8))}px`;
    colTip.style.top = `${b.bottom + 6}px`;
  };
  show();
  // a player's season detail (player_seasons.json, the largest file after the line-up history) is
  // fetched on the first hover: "Loading…" until it's in, then the text if the tip is still on this cell
  if (!h.dataset.tip && !state.playerSeasons) {
    loadPlayerSeasons();
    state.playerSeasonsLoading.then(() => { if (!colTip.hidden && colTip.cell === h && h.isConnected) show(); });
  }
});
$("#table-wrap").addEventListener("mouseout", (e) => {
  const tip = "th[data-tip], td.tip-cell";
  if (e.target.closest(tip) && e.relatedTarget?.closest?.(tip) !== e.target.closest(tip)) colTip.hidden = true;
});
$("#table-wrap").addEventListener("scroll", () => { colTip.hidden = true; }, true);

$("#table-wrap").addEventListener("click", (e) => {
  if (e.target.closest("[data-years]")) {
    state.playerYears = !state.playerYears;
    storeFlag("playerYears", state.playerYears);
    return renderTable();
  }
  const th = e.target.closest("th[data-sort]");
  if (th) {
    if (state.tableView === "players") state.playerSort = th.dataset.sort; else state.tableSort = th.dataset.sort;
    return renderTable();
  }
  if (e.target.closest("a")) return;
  const tr = e.target.closest("tr[data-team]");
  if (tr) openTeam(Number(tr.dataset.team));
});
$("#team-modal").addEventListener("click", (e) => {
  if (e.target.id === "team-modal" || e.target.closest(".modal-close")) $("#team-modal").hidden = true;
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#team-modal").hidden = true; });
// Sortable column headers and folding group headers from the keyboard: Enter or Space is a click.
// Most of them are redrawn by it, so focus goes back to the same header afterwards
document.addEventListener("keydown", (e) => {
  const el = e.target;
  if ((e.key !== "Enter" && e.key !== " ") || !el.matches?.("th.sortable, .comp-group-header, .tip-day")) return;
  e.preventDefault();
  const attr = [...el.attributes].find((a) => /^data-\w*(sort|fold)$/.test(a.name));
  const again = attr && `.panel[data-active="true"] [${attr.name}="${CSS.escape(attr.value)}"]`;
  el.click();
  if (again && !el.isConnected) document.querySelector(again)?.focus();
});

// Until the data is in, the header names the tab the address asks for
$("#app-title").textContent = document.querySelector(`nav.tabs [data-tab="${ROUTE_TABS[location.hash.match(/^#\/([\w-]+)$/)?.[1]] || ""}"]`)?.textContent
  ?? (/^#\/players/.test(location.hash) ? "Players" : location.hash.startsWith("#/") && !location.hash.startsWith("#/clubs") ? "" : "Clubs");
loadData();
