// My FPL team (web/src/routes/(app)/my-fpl-team): the owner's team with a transfer plan and chip
// advice, worked out here in the browser by fplPlanner.js. "I've made these transfers" saves a lock
// for the gameweek to the owner's account, and the plan then starts from the squad after them,
// until an FPL update reads the transfers from FPL itself.
import { Fragment, useEffect, useMemo, useState } from 'react';
import { shortName } from '../../../web/src/lib/club.ts';
import { CHIP_GAIN, CHIP_NAMES, FPL_POS, FPL_STATUS, type Lock, type PredDoc, type TeamDoc } from '../../../web/src/lib/fantasy.ts';
import * as Planner from '../../../web/src/lib/fplPlanner.js';
import type { ChipAdvice, Move, Plan, PlanPlayer, Prep } from '../../../web/src/lib/fplPlanner.js';
import { OwnerGate, Scroll } from './FantasyParts.tsx';
import { LocalTime } from './LocalTime.tsx';
import { lockTransfers, setLocks, useOwner, type Owner } from './owner.ts';

type Result = { prep: Prep; plan: Plan; chips: ChipAdvice[]; lock: Lock | null; ft: number };
const ORDER: Record<string, number> = { G: 0, D: 1, M: 2, F: 3 };
const money = (tenths: number) => `£${(tenths / 10).toFixed(1)}m`;

export function MyTeamPage({ email }: { email: string | null }) {
	const owner = useOwner(email);
	const t = owner.team, d = owner.fpl;
	return <div id="myteam-body">
		{owner.status !== 'ok' ? <div className="stats-card"><OwnerGate owner={owner} label="My FPL team" signedIn={!!email} /></div>
			: !t ? <div className="stats-card"><div className="stats-note">The team appears after the next FPL update.</div></div>
			: !d ? <div className="stats-card"><div className="stats-note">No predictions for the coming gameweeks yet.</div></div>
			: <Team owner={owner} t={t} d={d} />}
	</div>;
}

function Team({ owner, t, d }: { owner: Owner; t: TeamDoc; d: PredDoc }) {
	const locks = useMemo(() => new Map(owner.locks.filter((x) => x.season === t.season).map((x) => [x.event_id, x])), [owner.locks, t]);
	// free transfers: FPL's count less any already made there, unless changed here
	const [ftPicked, setFtPicked] = useState<number | null>(null);
	const [busy, setBusy] = useState(false), [msg, setMsg] = useState('');
	const ftFpl = Math.max(t.free_transfers - t.made.length, 0);
	// null: planning; false: couldn't
	const [r, setR] = useState<Result | null | false>(null);
	const lock = locks.get(t.next_event) || null, ftWanted = ftPicked ?? ftFpl;
	// The search takes a moment: "Planning…" is drawn first
	useEffect(() => {
		setR(null);
		const timer = setTimeout(() => {
			try {
				const prep = Planner.prepare(d, t);
				if (!prep) { setR(false); return; }
				let first: Move[] | null = null;
				if (lock) {
					// once FPL shows transfers for the week, its squad already has them: the lock only marks the week done
					first = t.made.length ? [] : lock.transfers.map((m) => ({ out: m.out, in: m.in }));
					if (first.length && !Planner.apply(prep.ctx, prep.start, first)) first = [];
				}
				const plan = Planner.plan(prep, { ft: ftWanted, first });
				setR({ prep, plan, chips: Planner.chipAdvice(prep, plan, t.chips, { locked: !!lock }), lock, ft: ftWanted });
			} catch (err) { console.error(err); setR(false); }
		}, 20);
		return () => clearTimeout(timer);
	}, [t, d, lock, ftWanted]);

	const passed = new Date(t.next_deadline) <= new Date();
	const ftNow = r ? r.ft : ftWanted;
	const code = (id: number | string) => d.teams[id]?.[1] || '';

	async function lockIn(undo: boolean) {
		if (!r || busy) return;
		const res0 = r, P = (id: number) => res0.prep.ctx.players.get(id) as PlanPlayer;
		const transfers = res0.plan.weeks[0].moves.map((m) => ({ out: m.out, in: m.in, out_name: P(m.out).name, in_name: P(m.in).name, sell: res0.prep.start.sell[m.out], buy: P(m.in).price }));
		setBusy(true); setMsg('');
		const res = await lockTransfers({ undo, season: t.season, event: t.next_event, transfers: undo ? undefined : transfers });
		setBusy(false);
		if (!res) { setMsg("Couldn't reach the database: nothing was saved."); return; }
		if (!res.ok) { setMsg(res.error || "Couldn't save that just now."); return; }
		const others = owner.locks.filter((x) => !(x.season === t.season && x.event_id === t.next_event));
		setLocks(undo ? others : [...others, { season: t.season, event_id: t.next_event, transfers, locked_at: res.locked_at || new Date().toISOString() }]);
	}

	return <>
		<div className="stats-card mt-head">
			<div className="mt-title"><b>{t.name}</b>{' '}
				<span>GW{t.next_event} deadline <LocalTime iso={t.next_deadline} show="day" />, <LocalTime iso={t.next_deadline} show="time" />{passed ? ' · passed: the page catches up at the next FPL update' : ''}</span></div>
			<div className="mt-stats">
				<div><span className="stats-label">Bank</span><b>{money(t.bank)}</b></div>
				<div><label className="stats-label" htmlFor="mt-ft" title="Worked out from your FPL history. If FPL shows a different number, change it here.">Free transfers</label>
					<select id="mt-ft" className="mt-select" value={ftNow} onChange={(e) => { const n = +e.currentTarget.value; setFtPicked(n === ftFpl ? null : n); }}>
						{[0, 1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</select></div>
				<div><span className="stats-label">Points</span><b>{t.overall_points ?? '–'}</b></div>
				<div><span className="stats-label">Overall rank</span><b>{t.overall_rank ? t.overall_rank.toLocaleString('en-GB') : '–'}</b></div>
			</div>
		</div>
		{r === null ? <div className="stats-card"><div className="stats-note">Planning…</div></div>
			: !r ? <div className="stats-card"><div className="stats-note">Couldn't plan: the predictions don't cover the next gameweek yet.</div></div>
			: planned(r)}
	</>;

	function planned(r: Result) {
		const P = (id: number) => r.prep.ctx.players.get(id) as PlanPlayer;
		const nm = (p: PlanPlayer) => (p.fpl ? p.name : shortName(p.name));
		const fix = (p: PlanPlayer, k: number) => (p.fixtures[k].length ? p.fixtures[k].map((x) => (x.home ? code(x.opponent) : code(x.opponent).toLowerCase())).join(' ') : '–');
		const tag = (p: PlanPlayer) => (p.status && p.status !== 'a' ? (p.status === 'd' ? `${p.chance ?? 50}%` : FPL_STATUS[p.status] || 'Doubtful') : p.missing ? 'No prediction' : '');
		const before = (k: number) => (k === 0 ? r.prep.start : r.plan.weeks[k - 1]);
		const gainOf = (m: Move, k: number) => Planner.moveGain(r.prep, before(k), m, k);
		// a chip's squad against the planned one: who goes, who comes
		const chipSwaps = (a: ChipAdvice): [number, number][] => {
			const best = a.best;
			if (!best?.squad || a.verdict === 'hold') return [];
			const from = before(best.k).squad, out = from.filter((id) => !best.squad!.includes(id)), inn = best.squad.filter((id) => !from.includes(id));
			return out.map((id, i) => [id, inn[i]]);
		};
		const doubt = (p: PlanPlayer) => tag(p) && <>{' '}<span className="bet-tag warn">{tag(p)}</span></>;
		const card = (p: PlanPlayer, captain: number, vice: number) =>
			<div key={p.id} className="mt-player"><span className="mt-nm">{nm(p)}{p.id === captain ? <>{' '}<b className="mt-c" title="Captain">C</b></> : p.id === vice ? <>{' '}<b className="mt-c v" title="Vice-captain">V</b></> : null}</span>
				<small>{fix(p, 0)} · {p.xp[0].toFixed(1)}</small>{doubt(p)}</div>;

		const w0 = r.plan.weeks[0], H = r.plan.weeks.length, lu = w0.lineup, ctx = r.prep.ctx;
		return <>
			{/* this week */}
			<div className="stats-card">
				<div className="stats-label">GW{w0.gw} transfers{r.lock ? ' · locked in' : ''}</div>
				{t.made.length > 0 && <div className="stats-note">Already made in FPL: {t.made.map((m) => `${m.out_name} → ${m.in_name}`).join(', ')}.</div>}
				{w0.moves.length ? w0.moves.map((m) => {
					const o = P(m.out), i = P(m.in), gain = gainOf(m, 0);
					return <div key={m.out} className="mt-move"><span><span className="mt-nm">{nm(o)}</span> <small>{FPL_POS[o.pos]} · sell {money(before(0).sell[m.out])}</small></span>
						<span className="mt-arrow" aria-label="for">→</span>
						<span><span className="mt-nm">{nm(i)}</span> <small>{code(i.team)} · {money(i.price)}</small>{doubt(i)}</span>
						{gain != null && <b className="mt-gain" title="Expected points gained over the plan's weeks, this transfer alone">{gain >= 0 ? '+' : '−'}{Math.abs(gain).toFixed(1)}</b>}</div>;
				}) : <p className="fpl-text">{r.lock ? 'No more transfers this week.' : `Roll the transfer: nothing gains enough over the next ${H} gameweeks. You'll have ${Math.min(Planner.MAX_FT, ftNow + 1)} free next week.`}</p>}
				{w0.hits > 0 && <div className="stats-note mt-warn">Costs a {w0.hits}-point hit: worth it over the {H} gameweeks.</div>}
				<div className="stats-note">Bank after: {money(w0.bank)}.</div>
				{r.lock
					? <div className="mt-locked"><span>✓ Locked in <LocalTime iso={r.lock.locked_at} show="day" />, <LocalTime iso={r.lock.locked_at} show="time" /></span>
						{!passed && <button type="button" className="filter-chip" id="mt-unlock" disabled={busy} onClick={() => lockIn(true)}>Undo</button>}</div>
					: !passed && <>
						<div className="mt-lock">
							<button type="button" className="mt-btn" id="mt-lock" disabled={busy} onClick={() => lockIn(false)}>{w0.moves.length ? "I've made these transfers" : 'Lock in: no transfers'}</button></div>
						<div className="stats-note">Made different ones? Lock in anyway: the next FPL update (07:00, 13:00 and 19:00 UTC) reads what you actually did.</div>
					</>}
				{msg && <div className="stats-note mt-warn" role="alert">{msg}</div>}
			</div>

			{/* line-up for the coming gameweek */}
			<div className="stats-card">
				<div className="stats-label">GW{w0.gw} line-up · {lu.points.toFixed(1)} expected points</div>
				<div className="mt-pitch">
					{['G', 'D', 'M', 'F'].map((pos) => <div key={pos} className="mt-row">{lu.xi.map(P).filter((p) => p.pos === pos).map((p) => card(p, lu.captain, lu.vice))}</div>)}
				</div>
				<div className="stats-label mt-sub">Bench, in order</div>
				<div className="mt-row mt-bench">{lu.bench.map(P).map((p) => card(p, lu.captain, lu.vice))}</div>
			</div>

			{/* the plan */}
			<div className="stats-card">
				<div className="stats-label">Plan · next {H} gameweeks</div>
				<Scroll><table className="calib-table mt-plan">
					<thead><tr><th>GW</th><th title="Free transfers that week">Free</th><th>Transfers</th><th>Hit</th><th>Captain</th><th>Pts</th></tr></thead>
					<tbody>
						{r.plan.weeks.map((w, k) => <tr key={w.gw}><td>GW{w.gw}{k === 0 && r.lock ? ' ✓' : ''}</td><td>{w.ft}</td>
							<td className="mt-plan-moves">{w.moves.length ? w.moves.map((m, j) => <Fragment key={m.out}>{j > 0 && <br />}{nm(P(m.out))} → {nm(P(m.in))}</Fragment>) : <span className="dim-text">Roll</span>}</td>
							<td>{w.hits ? `−${w.hits}` : ''}</td><td>{nm(P(w.lineup.captain))}</td><td><b>{w.points.toFixed(1)}</b></td></tr>)}
					</tbody></table></Scroll>
				<div className="stats-note">{r.plan.total.toFixed(1)} expected points over GW{r.plan.weeks[0].gw}–{r.plan.weeks[H - 1].gw},
					{' '}{(r.plan.total - r.plan.hold).toFixed(1)} more than making no transfers. Later weeks are a sketch: each week the plan is worked out again with the latest predictions.</div>
			</div>

			{/* chips */}
			<div className="stats-card">
				<div className="stats-label">Chips</div>
				{r.chips.map((a) => {
					const b = a.best, gainText = CHIP_GAIN[a.name];
					if (a.played != null && !a.options)
						return <div key={a.name} className="mt-chip"><div><b>{CHIP_NAMES[a.name]}</b><span className="fpl-badge">PLAYED GW{a.played}</span></div></div>;
					if (a.options && a.verdict === 'later' && a.window)
						return <div key={a.name} className="mt-chip"><div><b>{CHIP_NAMES[a.name]}</b><span className="fpl-badge">FROM GW{a.window[0]}</span></div>
							<div className="stats-note">Can be played GW{a.window[0]}–{a.window[1]}: after the gameweeks predicted so far.</div></div>;
					if (!a.options || !a.window) return null;
					const others = a.options.filter((o) => o !== b).slice(0, 4).map((o) => `GW${o.gw} +${o.gain.toFixed(1)}`).join(' · ');
					const swaps = chipSwaps(a);
					return <div key={a.name} className="mt-chip">
						<div><b>{CHIP_NAMES[a.name]}</b>{a.verdict === 'play' && b ? <span className="fpl-badge pass">PLAY GW{b.gw}</span> : a.verdict === 'last' && b ? <span className="fpl-badge pass">LAST CHANCE: GW{b.gw}</span> : <span className="fpl-badge">HOLD</span>}</div>
						<div className="stats-note">
							{a.verdict === 'play' && b ? <>+{b.gain.toFixed(1)} expected points {gainText}.</>
								: a.verdict === 'last' && b ? <>+{b.gain.toFixed(1)} expected points {gainText}: its window closes after GW{a.window[1]}, so play it in its best week left.</>
								: b ? <>Best week so far is GW{b.gw} at +{b.gain.toFixed(1)} {gainText}; it's worth playing from about +{Planner.CHIP_PLAY[a.name]}, usually a double gameweek. Play by GW{a.window[1]}.</>
								: <>No week left for it in the predictions. Play by GW{a.window[1]}.</>}
							{others && <>{' '}Other weeks: {others}.</>}</div>
						{swaps.length > 0 && <details className="mt-details"><summary>The {CHIP_NAMES[a.name]} squad's changes</summary>
							{swaps.map(([out, inn]) => <div key={out} className="mt-move"><span className="mt-nm">{nm(P(out))}</span><span className="mt-arrow">→</span><span className="mt-nm">{nm(P(inn))}</span></div>)}
						</details>}
					</div>;
				})}
				<div className="stats-note">Predictions reach GW{ctx.weeks[ctx.weeks.length - 1].id}, so the advice moves as later gameweeks come into view, and double gameweeks only show once FPL schedules them. One chip a gameweek.</div>
			</div>

			{/* squad by week */}
			<div className="stats-card">
				<div className="stats-label">Your squad · expected points</div>
				<Scroll><table className="calib-table mt-squad">
					<thead><tr><th>Player</th><th>Pos</th><th>Price</th>{ctx.weeks.slice(0, H).map((g) => <th key={g.id}>GW{g.id}</th>)}</tr></thead>
					<tbody>
						{[...r.prep.start.squad].map(P).sort((x, y) => ORDER[x.pos] - ORDER[y.pos] || y.xp[0] - x.xp[0]).map((p) =>
							<tr key={p.id}><td className="mt-nm-cell"><span className="mt-nm">{nm(p)}</span>{doubt(p)}</td><td>{FPL_POS[p.pos]}</td>
								<td title={`Selling price ${money(r.prep.start.sell[p.id])}`}>{money(p.price)}</td>
								{ctx.weeks.slice(0, H).map((g, k) => <td key={g.id} className={`fpl-gw${p.fixtures[k].length > 1 ? ' double' : ''}`}>{p.fixtures[k].length ? p.xp[k].toFixed(1) : '–'}<span>{fix(p, k)}</span></td>)}</tr>)}
					</tbody></table></Scroll>
			</div>

			<div className="stats-note mt-foot">
				Expected points are {d.model}'s, from the FPL tab. The plan searches the next {H} gameweeks for the transfers that add the most:
				each week it rolls the free transfer or makes one, two or three moves, and a move beyond the free ones costs 4 points.
				A player FPL lists as out with no expected points in any of those weeks is sold in the first week, even at a cost.
				A squad is scored by its best line-up with the captain doubled, plus a little for the bench; each later week counts 10% less than the one before,
				and a free transfer still banked at the end is worth 1.5 points. Selling prices keep half of any rise, as FPL does.
				Squad, bank, free transfers and chips come from FPL (updated at 07:00, 13:00 and 19:00 UTC). A guide, not advice.</div>
		</>;
	}
}
