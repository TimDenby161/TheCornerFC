"use strict";
// My FPL team: transfer plan and chip advice from the fantasy model's expected points
// (fpl_predictions.json) and the owner's squad (fpl_team.json). Pure functions, no page code:
// app.js draws the page, tests/fpl_planner.test.mjs runs this under node.
//
// Plan: a beam search over the next HORIZON gameweeks. Each week every kept plan may roll its
// free transfer, or make the best one, two or (with 3+ free) three transfers; a transfer beyond
// the free ones costs HIT points. A squad is scored by its best legal XI (captain doubled) plus a
// little for the bench, later weeks weighted down by DECAY. The constants are judgment, not fitted.
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.FplPlanner = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  const HORIZON = 6;          // weeks the transfer plan looks ahead
  const DECAY = 0.9;          // weight of each later week: predictions further out assume today's form and fitness
  const BENCH_WEIGHT = 0.1;   // bench points count a little: they come on when a starter doesn't play
  const FT_VALUE = 1.5;       // a free transfer still banked at the end of the plan
  const HIT = 4, MAX_FT = 5, CLUB_LIMIT = 3;
  const BEAM = 10, SINGLES = 8, DOUBLES = 6, CANDIDATES = 10, POOL = 60;
  const MIN_GAIN = 0.05;
  // A chip is advised for a week once its expected gain there reaches this, else held (unless its
  // window closes within the predictions). Set above an ordinary week's: a bench is worth ~12 and
  // a captain ~7 most weeks, so these want a double gameweek or a standout fixture.
  const CHIP_PLAY = { "3xc": 10, bboost: 18, freehit: 12, wildcard: 15 };
  const CHIP_ORDER = ["wildcard", "freehit", "bboost", "3xc"];
  const WILDCARD_WEEKS = 4;   // wildcard gain is checked for the first few weeks only

  // ---- data
  // Players keyed by API-Football id (negative FPL id for a squad player we can't match), with
  // expected points per week in view (weeks: FPL gameweeks from the next deadline on)
  function prepare(pred, team) {
    const start = team.next_event;
    const weeks = pred.gameweeks.map((g, idx) => ({ id: g.id, first_kickoff: g.first_kickoff, idx })).filter((g) => g.id >= start);
    if (!weeks.length) return null;
    const H = Math.min(HORIZON, weeks.length);
    const kOf = new Map(weeks.map((g, k) => [g.idx, k]));
    const f = Object.fromEntries(pred.fields.map((k, i) => [k, i]));
    const c = Object.fromEntries(pred.cell_fields.map((k, i) => [k, i]));
    const players = new Map();
    const blank = () => ({ xp: new Array(weeks.length).fill(0), fixtures: weeks.map(() => []) });
    pred.players.forEach((r, i) => {
      if (!r[f.fpl_position] || r[f.price] == null) return;       // FPL doesn't list him: can't be bought
      const p = { id: r[f.player], name: r[f.name], pos: r[f.fpl_position], team: r[f.team], price: r[f.price],
        status: r[f.fpl_status], chance: r[f.fpl_chance], ...blank() };
      for (const cell of pred.cells[i]) {
        const k = kOf.get(cell[c.gw]);
        if (k == null) continue;
        p.xp[k] += cell[c.xp];
        p.fixtures[k].push({ opponent: cell[c.opponent], home: cell[c.home] });
      }
      players.set(p.id, p);
    });
    const squad = [], sell = {};
    for (const s of team.squad) {
      const id = s.api ?? -s.fpl;
      const known = players.get(id);
      const p = { ...(known || { id, pos: s.pos, team: s.team ?? `fpl${s.fpl_team}`, missing: true, ...blank() }),
        name: s.name, fpl: s.fpl, price: s.price, status: s.status, chance: s.chance, news: s.news };
      players.set(id, p);
      squad.push(id);
      sell[id] = s.sell;
    }
    const ctx = { weeks, H, players, pool: { G: [], D: [], M: [], F: [] } };
    for (const p of players.values()) {
      if (!p.missing) ctx.pool[p.pos].push(p);
      // p.rem[k]: weighted points from week k to the end of the plan (orders transfer candidates)
      p.rem = new Array(H + 1).fill(0);
      for (let k = H - 1; k >= 0; k--) p.rem[k] = p.rem[k + 1] + DECAY ** k * p.xp[k];
    }
    return { ctx, start: { squad, sell, bank: team.bank } };
  }

  // ---- scoring
  // Best legal XI (1 GK, 3+ DEF, 2+ MID, 1+ FWD): the top keeper, the minimum of each outfield
  // line, then the best of the rest. Bench: second keeper first, then outfield by points.
  function lineup(ctx, squad, k) {
    const by = { G: [], D: [], M: [], F: [] };
    for (const id of squad) { const p = ctx.players.get(id); by[p.pos].push(p); }
    for (const pos in by) by[pos].sort((a, b) => b.xp[k] - a.xp[k]);
    const xi = [by.G[0], ...by.D.slice(0, 3), ...by.M.slice(0, 2), by.F[0]].filter(Boolean);
    const rest = [...by.D.slice(3), ...by.M.slice(2), ...by.F.slice(1)].sort((a, b) => b.xp[k] - a.xp[k]);
    const need = 11 - xi.length;
    xi.push(...rest.slice(0, need));
    const bench = [by.G[1], ...rest.slice(need)].filter(Boolean);
    const order = [...xi].sort((a, b) => b.xp[k] - a.xp[k]);
    const sum = (ps) => ps.reduce((a, p) => a + p.xp[k], 0);
    const outfieldBench = bench.filter((p) => p.pos !== "G");
    return { xi: xi.map((p) => p.id), bench: bench.map((p) => p.id), captain: order[0]?.id, vice: order[1]?.id,
      points: sum(xi) + (order[0]?.xp[k] || 0), captainPts: order[0]?.xp[k] || 0,
      benchPts: sum(bench), score: sum(xi) + (order[0]?.xp[k] || 0) + BENCH_WEIGHT * sum(outfieldBench) };
  }
  const weighted = (ctx, squad, k0, k1, base = 0) => {
    let v = 0;
    for (let k = k0; k < k1; k++) v += DECAY ** (k - base) * lineup(ctx, squad, k).score;
    return v;
  };

  // ---- transfers
  function clubsOf(ctx, squad) {
    const m = new Map();
    for (const id of squad) { const t = ctx.players.get(id).team; m.set(t, (m.get(t) || 0) + 1); }
    return m;
  }
  // moves [{out, in}] -> the new state, or null if over budget or over a club's limit
  function apply(ctx, st, moves) {
    let bank = st.bank;
    const squad = [...st.squad], sell = { ...st.sell };
    for (const m of moves) {
      const i = squad.indexOf(m.out);
      if (i < 0 || squad.includes(m.in)) return null;
      const inP = ctx.players.get(m.in);
      if (!inP || inP.pos !== ctx.players.get(m.out).pos) return null;
      bank += sell[m.out] - inP.price;
      delete sell[m.out];
      squad[i] = m.in;
      sell[m.in] = inP.price;
    }
    if (bank < 0) return null;
    for (const n of clubsOf(ctx, squad).values()) if (n > CLUB_LIMIT) return null;
    return { squad, sell, bank };
  }
  // The best single, double and (optionally) triple transfers by obj(squad), candidates ordered by quick(player)
  function bestMoves(ctx, st, obj, quick, { singles = SINGLES, doubles = DOUBLES, triples = false } = {}) {
    const base = obj(st.squad);
    const inSquad = new Set(st.squad);
    const clubs = clubsOf(ctx, st.squad);
    const cands = {};
    for (const pos in ctx.pool) cands[pos] = ctx.pool[pos].filter((p) => !inSquad.has(p.id)).sort((a, b) => quick(b) - quick(a)).slice(0, POOL);
    const tryMoves = (moves, list) => {
      const next = apply(ctx, st, moves);
      if (!next) return;
      const gain = obj(next.squad) - base;
      if (gain > MIN_GAIN) list.push({ moves, gain, state: next });
    };
    const one = [];
    for (const out of st.squad) {
      const o = ctx.players.get(out), budget = st.bank + st.sell[out];
      let n = 0;
      for (const c of cands[o.pos]) {
        if (c.price > budget || (c.team !== o.team && (clubs.get(c.team) || 0) >= CLUB_LIMIT)) continue;
        tryMoves([{ out, in: c.id }], one);
        if (++n >= CANDIDATES) break;
      }
    }
    one.sort((a, b) => b.gain - a.gain);
    const two = [];
    if (doubles) {
      const top = one.slice(0, 12);
      for (let i = 0; i < top.length; i++) for (let j = i + 1; j < top.length; j++) {
        const [a, b] = [top[i].moves[0], top[j].moves[0]];
        if (a.out !== b.out && a.in !== b.in) tryMoves([a, b], two);
      }
      // two sold to fund two bought: pairs ranked by quick first, the best few scored exactly
      const funded = [];
      for (let i = 0; i < st.squad.length; i++) for (let j = i + 1; j < st.squad.length; j++) {
        const [o1, o2] = [ctx.players.get(st.squad[i]), ctx.players.get(st.squad[j])];
        const budget = st.bank + st.sell[o1.id] + st.sell[o2.id];
        let best = null;
        for (const c1 of cands[o1.pos].slice(0, 8)) for (const c2 of cands[o2.pos].slice(0, 8)) {
          if (c1 === c2 || c1.price + c2.price > budget) continue;
          const est = quick(c1) + quick(c2) - quick(o1) - quick(o2);
          if (!best || est > best.est) best = { est, moves: [{ out: o1.id, in: c1.id }, { out: o2.id, in: c2.id }] };
        }
        if (best && best.est > 0) funded.push(best);
      }
      funded.sort((a, b) => b.est - a.est).slice(0, 15).forEach((f) => tryMoves(f.moves, two));
    }
    const seen = new Set();
    const uniq = (list) => list.sort((a, b) => b.gain - a.gain).filter((m) => {
      const key = m.moves.map((x) => `${x.out}>${x.in}`).sort().join();
      return !seen.has(key) && seen.add(key);
    });
    const res = { singles: uniq(one).slice(0, singles), doubles: uniq(two).slice(0, doubles), triples: [] };
    if (triples) {
      for (const d of res.doubles.slice(0, 3)) {
        const sold = new Set(d.moves.map((m) => m.out));
        const more = bestMoves(ctx, d.state, obj, quick, { singles: 3, doubles: 0 }).singles
          .find((s) => !sold.has(s.moves[0].in) && !d.moves.some((m) => m.in === s.moves[0].out));
        if (more) tryMoves([...d.moves, ...more.moves], res.triples);
      }
      res.triples = uniq(res.triples).slice(0, 3);
    }
    return res;
  }

  // ---- plan
  // ft: free transfers for the first week (after any already made in FPL). first: moves fixed for
  // the first week (the transfers locked in; [] = locked with none), or null to plan it too.
  function plan(prep, { ft, first = null } = {}) {
    const { ctx, start } = prep;
    const H = ctx.H;
    const key = (s) => [...s.squad].sort((a, b) => a - b).join() + `|${s.ft}`;
    let beam = [{ ...start, ft, steps: [], acc: 0 }];
    for (let k = 0; k < H; k++) {
      const obj = (sq) => weighted(ctx, sq, k, H);
      const quick = (p) => p.rem[k];
      const next = new Map();
      for (const s of beam) {
        const options = k === 0 && first ? [{ moves: first }]
          : (({ singles, doubles, triples }) => [{ moves: [] }, ...singles, ...doubles, ...triples])(
            bestMoves(ctx, s, obj, quick, { triples: s.ft >= 3 }));
        for (const opt of options) {
          const st = opt.moves.length ? opt.state || apply(ctx, s, opt.moves) : s;
          if (!st) continue;
          const n = opt.moves.length;
          const hits = Math.max(0, n - s.ft) * HIT;
          const ftNext = Math.min(MAX_FT, Math.max(s.ft - n, 0) + 1);
          const acc = s.acc + DECAY ** k * lineup(ctx, st.squad, k).score - hits;
          const cand = { squad: st.squad, sell: st.sell, bank: st.bank, ft: ftNext, acc,
            steps: [...s.steps, { moves: opt.moves, hits, ft: s.ft }],
            est: acc + weighted(ctx, st.squad, k + 1, H) + FT_VALUE * ftNext };
          const kk = key(cand);
          if (!next.has(kk) || next.get(kk).est < cand.est) next.set(kk, cand);
        }
      }
      beam = [...next.values()].sort((a, b) => b.est - a.est).slice(0, BEAM);
    }
    const best = beam.reduce((a, b) => (b.acc + FT_VALUE * b.ft > a.acc + FT_VALUE * a.ft ? b : a));
    // replay the chosen steps to report each week's squad, bank and line-up
    let st = { ...start };
    const weeks = best.steps.map((step, k) => {
      if (step.moves.length) st = apply(ctx, st, step.moves);
      const lu = lineup(ctx, st.squad, k);
      return { k, gw: ctx.weeks[k].id, moves: step.moves, hits: step.hits, ft: step.ft, squad: st.squad, sell: st.sell,
        bank: st.bank, lineup: lu, points: lu.points - step.hits };
    });
    const hold = ctx.weeks.slice(0, H).reduce((a, _, k) => a + lineup(ctx, start.squad, k).points, 0);
    return { weeks, total: weeks.reduce((a, w) => a + w.points, 0), hold };
  }

  // Each move's own gain over the plan's weeks, holding the rest of the squad (for display)
  function moveGain(prep, st, move, k) {
    const { ctx } = prep;
    const next = apply(ctx, st, [move]);
    if (!next) return null;
    let v = 0;
    for (let j = k; j < ctx.H; j++) v += lineup(ctx, next.squad, j).points - lineup(ctx, st.squad, j).points;
    return v;
  }

  // ---- chips
  function climb(ctx, st, obj, quick) {
    for (let i = 0; i < 30; i++) {
      const m = bestMoves(ctx, st, obj, quick, { singles: 1, doubles: 1 });
      const pick = [...m.singles, ...m.doubles].sort((a, b) => b.gain - a.gain)[0];
      if (!pick) break;
      st = pick.state;
    }
    return st;
  }
  // chips: fpl_team.json's chips. For each chip still to play, its expected gain in each week in
  // view with the planned squad, the week to play it, and whether to play it or hold it.
  // locked: the first week's transfers are done, so a Wildcard or Free Hit can't be played in it
  function chipAdvice(prep, planned, chips, { locked = false } = {}) {
    const { ctx } = prep;
    const W = ctx.weeks.length, first = ctx.weeks[0].id, last = ctx.weeks[W - 1].id;
    const at = (k) => planned.weeks[Math.min(k, planned.weeks.length - 1)];
    const squadAt = (k) => at(k).squad;
    const gains = {
      "3xc": (k) => lineup(ctx, squadAt(k), k).captainPts,
      bboost: (k) => lineup(ctx, squadAt(k), k).benchPts,
      freehit: (k) => {
        const w = at(k);
        const best = climb(ctx, { squad: w.squad, sell: w.sell, bank: w.bank }, (sq) => lineup(ctx, sq, k).points, (p) => p.xp[k]);
        return { gain: lineup(ctx, best.squad, k).points - lineup(ctx, w.squad, k).points, squad: best.squad };
      },
      // against the plan over the same weeks, hits included: a wildcard squad then kept as it is
      wildcard: (k) => {
        if (k >= WILDCARD_WEEKS) return null;
        const end = Math.min(k + ctx.H, W);
        const w = k === 0 ? prep.start : at(k - 1);
        const obj = (sq) => weighted(ctx, sq, k, end, k);
        const quick = (p) => { let v = 0; for (let j = k; j < end; j++) v += DECAY ** (j - k) * p.xp[j]; return v; };
        const best = climb(ctx, { squad: w.squad, sell: w.sell, bank: w.bank }, obj, quick);
        let kept = 0;
        for (let j = k; j < end; j++) kept += DECAY ** (j - k) * lineup(ctx, squadAt(j), j).score;
        kept -= planned.weeks.slice(k, end).reduce((a, x) => a + x.hits, 0);
        return { gain: obj(best.squad) - kept, squad: best.squad };
      },
    };
    const out = [];
    for (const name of CHIP_ORDER) {
      const windows = chips.filter((c) => c.name === name && c.stop >= first).sort((a, b) => a.start - b.start);
      const c = windows.find((w) => w.played == null);
      if (!c) { const p = windows.find((w) => w.played != null); out.push({ name, played: p?.played ?? null, window: p ? [p.start, p.stop] : null }); continue; }
      const options = [];
      for (let k = 0; k < W; k++) {
        const id = ctx.weeks[k].id;
        if (id < c.start || id > c.stop || (locked && k === 0 && (name === "wildcard" || name === "freehit"))) continue;
        const g = gains[name](k);
        if (g == null) continue;
        const r = typeof g === "number" ? { gain: g } : g;
        options.push({ k, gw: id, ...r });
      }
      options.sort((a, b) => b.gain - a.gain);
      out.push({ name, window: [c.start, c.stop], options, closes: c.stop <= last });
    }
    // one chip a gameweek: the bigger gain keeps the week, the other takes its next best
    const taken = new Set();
    for (const a of out.filter((a) => a.options?.length).sort((x, y) => y.options[0].gain / CHIP_PLAY[y.name] - x.options[0].gain / CHIP_PLAY[x.name])) {
      const pick = a.options.find((o) => !taken.has(o.gw));
      if (!pick) { a.verdict = "hold"; continue; }
      a.best = pick;
      a.verdict = pick.gain >= CHIP_PLAY[a.name] ? "play" : a.closes ? "last" : "hold";
      if (a.verdict !== "hold") taken.add(pick.gw);
    }
    for (const a of out) if (a.options && !a.options.length) a.verdict = "later";
    return out;
  }

  return { HORIZON, DECAY, HIT, MAX_FT, CHIP_PLAY, prepare, lineup, apply, bestMoves, plan, moveGain, chipAdvice };
});
