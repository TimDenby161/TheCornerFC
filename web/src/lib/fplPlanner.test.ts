// @ts-nocheck
// fplPlanner.js on a synthetic squad and pool (the old site's tests/fpl_planner.test.mjs, carried over)
import { expect, test } from 'vitest';
import * as P from './fplPlanner.js';

const assert = {
	equal: (a: unknown, b: unknown) => expect(a).toBe(b),
	deepEqual: (a: unknown, b: unknown) => expect(a).toEqual(b),
	ok: (a: unknown) => expect(a).toBeTruthy()
};
const GWS = [6, 7, 8, 9, 10, 11, 12, 13];

// players: [id, pos, team, price, xp per gameweek (number, or array by gameweek; 0 = blank), doubles: {gw: true}]
function world(players, { doubles = {} } = {}) {
  const pred = {
    gameweeks: GWS.map((id) => ({ id, first_kickoff: `2026-10-${String(id).padStart(2, "0")}T12:00:00Z` })),
    teams: {}, fields: ["player", "name", "team", "position", "fpl_position", "price", "fpl_status", "fpl_chance", "availability"],
    cell_fields: ["gw", "opponent", "home", "xp"], players: [], cells: [],
  };
  for (const [id, pos, team, price, xp] of players) {
    pred.players.push([id, `P${id}`, team, pos, pos, price, "a", null, null]);
    const cells = [];
    GWS.forEach((gw, i) => {
      const v = Array.isArray(xp) ? xp[i] : xp;
      if (!v) return;
      const n = doubles[id]?.includes(gw) ? 2 : 1;
      for (let j = 0; j < n; j++) cells.push([i, 999, true, v]);
    });
    pred.cells.push(cells);
  }
  return pred;
}
// A legal squad: 2 GK, 5 DEF, 5 MID, 3 FWD over five clubs (three each), 2.0 points a week, £5.0m
const SQUAD = [..."GGDDDDDMMMMMFFF"].map((pos, i) => [i + 1, pos, 100 + (i % 5), 50, 2]);
const team = (over = {}) => ({ next_event: 6, bank: 0, free_transfers: 1, made: [], chips: [],
  squad: SQUAD.map(([id, pos, t, price]) => ({ fpl: id, api: id, name: `P${id}`, pos, team: t, price, sell: price })), ...over });

test("line-up: one keeper, a legal shape, captain doubled, keeper first on the bench", () => {
  const pl = SQUAD.map((p) => [...p]);
  pl[7][4] = 9;                               // a midfielder at 9
  pl[12][4] = 0.5; pl[13][4] = 0.4;           // two weak forwards: only one has to start
  const prep = P.prepare(world(pl), team());
  const lu = P.lineup(prep.ctx, prep.start.squad, 0);
  const pos = (id) => prep.ctx.players.get(id).pos;
  const count = (p) => lu.xi.filter((id) => pos(id) === p).length;
  assert.equal(lu.xi.length, 11);
  assert.equal(count("G"), 1);
  assert.ok(count("D") >= 3 && count("M") >= 2 && count("F") >= 1);
  assert.equal(lu.captain, 8);
  assert.equal(pos(lu.bench[0]), "G");
  assert.ok(lu.bench.includes(14) && lu.bench.includes(13));
  assert.equal(lu.points, 9 * 2 + 10 * 2);                // the captain's 9 twice, ten others at 2: both weak forwards benched
});

test("transfers respect the budget and three players a club", () => {
  const pool = [[50, "M", 100, 90, 6], [51, "M", 100, 50, 6]];   // club 100 already has three
  const prep = P.prepare(world([...SQUAD, ...pool]), team({ bank: 10 }));
  assert.equal(P.apply(prep.ctx, prep.start, [{ out: 8, in: 50 }]), null);        // £9.0m for £5.0m + £1.0m
  assert.equal(P.apply(prep.ctx, prep.start, [{ out: 9, in: 51 }]), null);        // a fourth from club 100
  const ok = P.apply(prep.ctx, prep.start, [{ out: 11, in: 51 }]);                // selling club 100's own midfielder
  assert.ok(ok);
  assert.equal(ok.bank, 10);
});

test("plan makes a clear upgrade with the free transfer, and takes no hit for a small one", () => {
  const pool = [[60, "M", 200, 50, 6], [61, "F", 201, 50, 2.3]];
  const prep = P.prepare(world([...SQUAD, ...pool]), team());
  const plan = P.plan(prep, { ft: 1 });
  assert.deepEqual(plan.weeks[0].moves.map((m) => m.in), [60]);
  assert.equal(plan.weeks[0].hits, 0);
  assert.ok(plan.weeks.every((w) => w.hits === 0));
  assert.ok(plan.total > plan.hold);
});

test("plan rolls when nothing gains, and free transfers build to at most five", () => {
  const prep = P.prepare(world(SQUAD), team());
  const plan = P.plan(prep, { ft: 4 });
  assert.ok(plan.weeks.every((w) => !w.moves.length));
  assert.deepEqual(plan.weeks.map((w) => w.ft), [4, 5, 5, 5, 5, 5]);
});

test("a locked-in week keeps its transfers; the next week's free transfers follow FPL's rule", () => {
  const pool = [[60, "M", 200, 50, 6], [62, "D", 202, 50, 2.5]];
  const prep = P.prepare(world([...SQUAD, ...pool]), team());
  const plan = P.plan(prep, { ft: 1, first: [{ out: 3, in: 62 }] });
  assert.deepEqual(plan.weeks[0].moves, [{ out: 3, in: 62 }]);
  assert.equal(plan.weeks[1].ft, 1);
  assert.ok(plan.weeks[1].squad.includes(62));
  const none = P.plan(prep, { ft: 1, first: [] });
  assert.equal(none.weeks[0].moves.length, 0);
  assert.equal(none.weeks[1].ft, 2);
});

test("chips: a double gameweek gets Triple Captain and Bench Boost; played and later chips say so", () => {
  const pl = SQUAD.map((p) => [...p]);
  pl[7][4] = 6;                                          // the captain
  const doubles = Object.fromEntries(SQUAD.map(([id]) => [id, [9]]));   // everyone doubles in GW9
  const w = world(pl, { doubles });
  const chips = [{ name: "3xc", start: 1, stop: 19, played: null }, { name: "bboost", start: 1, stop: 19, played: null },
    { name: "wildcard", start: 2, stop: 19, played: 4 }, { name: "wildcard", start: 20, stop: 38, played: null },
    { name: "freehit", start: 20, stop: 38, played: null }];
  const prep = P.prepare(w, team({ chips }));
  const advice = Object.fromEntries(P.chipAdvice(prep, P.plan(prep, { ft: 1 }), chips).map((a) => [a.name, a]));
  assert.equal(advice["3xc"].best.gw, 9);
  assert.equal(advice["3xc"].verdict, "play");
  assert.equal(advice.bboost.options[0].gw, 9);           // its best week too, before one-chip-a-week moves it
  assert.equal(advice.freehit.verdict, "later");
  assert.equal(advice.wildcard.verdict, "later");                  // first one played; the second opens at GW20
  // one chip a gameweek: the two can't both be played in GW9
  const played = Object.values(advice).filter((a) => a.verdict === "play" || a.verdict === "last").map((a) => a.best.gw);
  assert.equal(new Set(played).size, played.length);
});

test("a squad player with no prediction counts as zero and can be sold", () => {
  const t = team();
  t.squad[12] = { ...t.squad[12], api: null, fpl: 999 };
  const prep = P.prepare(world([...SQUAD, [70, "F", 203, 50, 3]]), t);
  assert.ok(prep.ctx.players.get(-999).missing);
  const plan = P.plan(prep, { ft: 1 });
  assert.deepEqual(plan.weeks[0].moves, [{ out: -999, in: 70 }]);
});
