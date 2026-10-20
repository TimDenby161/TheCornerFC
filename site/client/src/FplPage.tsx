// The FPL page (web/src/routes/(app)/fpl): each Premier League player's predicted points by
// gameweek, for the site owner only, and the model's own test results under it
import { Fragment, useEffect, useMemo, useState, type ChangeEvent } from 'react';
import { FPL_PARTS, FPL_POS, FPL_SHOWN, fplList, fplSpan, oppCode, partLines, predRows, priceLabel, priceStops, signed, statusTag, teamOf, versus,
	type FplView, type Gameweek, type ListRow, type SortKey } from '../../../web/src/lib/fantasy.ts';
import { findingsView, type FindingsView, type FplFindings } from '../../../web/src/lib/fplFindings.ts';
import { stopIndex } from '../../../web/src/lib/playerFilters.ts';
import { day, FantasyWho, OwnerGate, Scroll, useFrozenColumns } from './FantasyParts.tsx';
import { LocalTime } from './LocalTime.tsx';
import { askKnown, markPlayer, useOwner, type Owner } from './owner.ts';

const SORTS: Record<string, [SortKey, string, string][]> = {
	gw: [['xp', 'Pts', ''], ['minutes', 'Mins', ''], ['goals', 'G', 'Expected goals'], ['assists', 'A', 'Expected assists']],
	multi: [['xp', 'Total', ''], ['value', 'Pts/£m', '']]
};
type Calib = FindingsView['startCalib'];
type Seg = FindingsView['byPosition'];

const CalibTable = ({ rows, unit, happened }: { rows: Calib; unit: string; happened: string }) =>
	<table className="calib-table"><thead><tr><th>Said</th><th>{unit}</th><th>{happened}</th><th></th></tr></thead><tbody>
		{rows.map((c, i) => <tr key={i}><td>{c.said}</td><td>{c.count}</td><td className={c.cls}>{c.hit}</td><td className="u-w70"><span className={`calib-bar cb-${c.bar}`}></span></td></tr>)}
	</tbody></table>;
const SegTable = ({ rows, label }: { rows: Seg; label: string }) =>
	<Scroll><table className="calib-table">
		<thead><tr><th>{label}</th><th>Rows</th><th>Model err</th><th>Last-5 err</th><th>PPG err</th><th>Model rank</th><th>Last-5 rank</th></tr></thead>
		<tbody>{rows.map((x) => <tr key={x.name}><td>{x.name}</td><td>{x.rows}</td><td className={x.cls}>{x.model}</td><td>{x.recent}</td><td>{x.ppg}</td><td>{x.rank}</td><td>{x.recentRank}</td></tr>)}</tbody>
	</table></Scroll>;

export function FplPage({ email, findings }: { email: string | null; findings: FplFindings | null }) {
	const owner = useOwner(email);
	const f = useMemo(() => (findings ? findingsView(findings) : null), [findings]);
	return <div id="fpl-body">
		{owner.status !== 'ok'
			? <div className="stats-card"><OwnerGate owner={owner} label="Predictions" signedIn={!!email} /></div>
			: <>
				{f && <details className={`stats-card fpl-verdict${f.ok ? ' ok' : ''}`}>
					<summary><span className="stats-label">Model status</span>{' '}
						<span className="fpl-verdict-line">{f.verdict}</span></summary>
					<p className="fpl-text">Our model predicts each Premier League player's fantasy points per match from expected minutes, our match predictions,
						each player's shots and chances, and clean-sheet odds. Tested on {f.testRows} player-matches since July 2024 that it had never seen,
						it beats the usual shortcuts clearly and its probabilities are well calibrated. It fails one check: goalkeepers come out too low because save points were left out.
						The predictions below use a later version (v1.4), which adds saves, injury news, bonus, cards, penalty saves and defensive contributions.
						It was designed after seeing these results, so it is now being tested on upcoming gameweeks before anyone should rely on it.</p>
				</details>}
				<Predictions owner={owner} />
				{!f ? <div className="empty-state">No FPL findings yet.</div> : <Findings f={f} />}
			</>}
	</div>;
}

function Predictions({ owner }: { owner: Owner }) {
	const d = owner.fpl;
	const [v, setV] = useState<FplView>({ pos: 'all', q: '', sort: 'xp', mode: 'gw', gw: 0, price: [null, null], mine: false, target: false });
	const [all, setAll] = useState(false), [open, setOpen] = useState<number | null>(null), [markMsg, setMarkMsg] = useState('');
	const change = (c: Partial<FplView>, keepAll = false) => { setV((x) => ({ ...x, ...c })); if (!keepAll) setAll(false); };
	const players = useMemo(() => (d ? predRows(d) : []), [d]);
	const gws = d?.gameweeks ?? [];
	const one = v.mode === 'gw';
	const span = d ? fplSpan(d, v) : [];
	const rows = useMemo(() => (d ? fplList(d, players, v, owner.marks) : []), [d, players, v, owner.marks]);
	const list = all ? rows : rows.slice(0, FPL_SHOWN);
	const cols = one ? 8 : 6 + span.length;
	const ids = list.map((r) => r.p.player).join();
	useEffect(() => { void askKnown(list.map((r) => r.p.player)); }, [ids]); // eslint-disable-line react-hooks/exhaustive-deps
	const frozen = useFrozenColumns();

	const gwLabel = (g: Gameweek) => (d?.source === 'fpl' ? `GW${g.id}` : `Round ${g.id}`);
	const count = (j: 0 | 1) => [...owner.marks.values()].filter((m) => m[j]).length;
	const setMode = (mode: string) => change({ mode, ...(mode !== 'gw' && (v.sort === 'minutes' || v.sort === 'goals' || v.sort === 'assists') ? { sort: 'xp' as const } : {}) });
	const step = (by: number) => change({ gw: Math.max(0, Math.min(v.gw + by, gws.length - 1)) }, true);

	// the price slider: a handle at either end leaves that end open, and the handles can't cross
	const stops = useMemo(() => priceStops(players), [players]);
	const top = stops.length - 1;
	const a = stopIndex(stops, v.price[0], 0), b = stopIndex(stops, v.price[1], 1);
	const at = (i: number) => Math.round((i / (top || 1)) * 100);
	const priced = (end: 0 | 1, e: ChangeEvent<HTMLInputElement>) => {
		const lo = end === 0 ? Math.min(+e.currentTarget.value, b) : a, hi = end === 1 ? Math.max(+e.currentTarget.value, a) : b;
		change({ price: [lo === 0 ? null : stops[lo], hi === top ? null : stops[hi]] });
	};
	const mark = async (r: ListRow, which: 0 | 1, e: ChangeEvent<HTMLInputElement>) => {
		setMarkMsg('');
		setMarkMsg(await markPlayer(r.p.player, which, e.currentTarget.checked));
	};

	if (!d || !d.players.length)
		return <div className="stats-card" id="fpl-next"><div className="stats-label">Predictions</div><div className="stats-note">No upcoming Premier League gameweeks yet.</div></div>;
	return <div className="stats-card" id="fpl-next">
		<div className="stats-label">Predicted points</div>
		<div className="fpl-filters">
			{[['gw', 'Gameweek'], ['2', 'Next 2'], ['5', 'Next 5'], ['10', 'Next 10']].map(([k, label]) =>
				<button key={k} type="button" className="filter-chip" aria-pressed={v.mode === k} onClick={() => setMode(k)}>{label}</button>)}
			{one
				? <span className="fpl-pager"><button type="button" className="filter-chip" aria-label="Previous gameweek" disabled={v.gw === 0} onClick={() => step(-1)}>◀</button>
					<span className="fpl-span">{gwLabel(gws[v.gw])} · {day(gws[v.gw].first_kickoff)}</span>
					<button type="button" className="filter-chip" aria-label="Next gameweek" disabled={v.gw === gws.length - 1} onClick={() => step(1)}>▶</button></span>
				: <span className="fpl-span">{gwLabel(gws[0])}–{gwLabel(gws[span.length - 1]).replace(/^\D+/, '')}</span>}
		</div>
		<div className="fpl-filters">
			{[['all', 'All'], ['G', 'GK'], ['D', 'DEF'], ['M', 'MID'], ['F', 'FWD']].map(([k, label]) =>
				<button key={k} type="button" className="filter-chip" aria-pressed={v.pos === k} onClick={() => change({ pos: k })}>{label}</button>)}
			<button type="button" className="filter-chip" aria-pressed={v.mine} onClick={() => change({ mine: !v.mine })}>My team {count(0)}</button>
			<button type="button" className="filter-chip" aria-pressed={v.target} onClick={() => change({ target: !v.target })}>Targets {count(1)}</button>
			<input type="search" className="table-search fpl-search" id="fpl-q" placeholder="Search players or clubs" aria-label="Search players or clubs"
				value={v.q} onChange={(e) => change({ q: e.currentTarget.value })} />
		</div>
		{top >= 1 && <div className="fpl-price" id="fpl-price">
			<div className="age-head"><span>Price</span><span className="rng-val">{priceLabel(stops, a, b)}</span></div>
			<div className="age-slider"><div className="age-track"><div className={`age-fill sx-${at(a)} sr-${100 - at(b)}`}></div></div>
				<input type="range" min="0" max={top} step="1" value={a} aria-label="Price: from" onChange={(e) => priced(0, e)} />
				<input type="range" min="0" max={top} step="1" value={b} aria-label="Price: to" onChange={(e) => priced(1, e)} /></div>
		</div>}
		{markMsg && <div className="stats-note mt-warn" id="fpl-mark-msg" role="alert">{markMsg}</div>}
		<div id="fpl-list">
			<Scroll>
				<table key={String(one)} className={`calib-table fpl-table${one ? '' : ' multi'}`} ref={frozen}>
					<thead><tr><th>#</th><th>Player</th><th title="In my team">Mine</th><th title="A player I want">Target</th>
						{SORTS[one ? 'gw' : 'multi'].map(([k, label, title]) =>
							<th key={k} title={title || undefined}><button type="button" className={`fpl-sort${v.sort === k ? ' on' : ''}`} aria-pressed={v.sort === k} aria-label={title || undefined} onClick={() => change({ sort: k }, true)}>{label}</button></th>)}
						{!one && span.map((i) => <th key={i} title={day(gws[i].first_kickoff)}>{gwLabel(gws[i])}</th>)}
					</tr></thead>
					<tbody>
						{list.length ? list.map((r, i) => <Fragment key={r.p.player}>{playerRows(r, i)}</Fragment>) : <tr><td colSpan={cols}>No players match.</td></tr>}
					</tbody>
				</table>
			</Scroll>
			{rows.length > FPL_SHOWN && <button type="button" className="show-all" id="fpl-more" onClick={() => setAll(!all)}>{all ? 'Show fewer' : `Show all ${rows.length}`}</button>}
		</div>
		<div className="stats-note">Points are our model's prediction with FPL's scoring rules for the player's FPL position: appearance, goals, penalties, assists, FPL assists, clean sheets,
			goals conceded, saves, penalty saves, cards, bonus and defensive contributions. Bonus is rebuilt from match stats (it tracks FPL's own closely).
			Defensive contributions combine each player's tackles, blocks and interceptions with his own FPL record this season, which also counts clearances.
			Penalties go mostly to each club's taker, from FPL's penalty order and who has taken them recently; a miss costs 2.
			FPL assists are the ones FPL gives that match stats don't: winning a penalty a teammate scores, and rebounds or deflections from a player's shot.
			Injuries use FPL's status: injured or suspended players are out until FPL's return date (or until FPL clears them), and doubtful players count at FPL's chance of playing for the next gameweek; match-day injury lists apply near kickoff.
			Click a player's points to see where they come from.
			{' '}{d.source === 'fpl' ? "Positions, prices, status and gameweeks come from FPL (updated nightly); players FPL doesn't list at their club are left out." : "FPL positions, prices and gameweeks appear after the first nightly FPL update; until then * marks our own position and rounds are the fixture list's."}
			{' '}In the multi-gameweek view, capitals are home games and lower case away; a double gameweek shows both. Predictions further ahead assume today's form and fitness.
			This is {d.model}, designed after the backtest below and still being tested on upcoming gameweeks: a guide, not a pick list.</div>
	</div>;

	function playerRows(r: ListRow, i: number) {
		const pd = d!;
		return <>
			<tr><td>{i + 1}</td>
				<FantasyWho owner={owner} id={r.p.player} name={r.p.name} team={r.p.team} teamName={teamOf(pd, r.p.team)} tag={statusTag(r.p)}
					line={one ? versus(pd, r.cells) : teamOf(pd, r.p.team)}
					meta={<span className="fpl-meta"><span title={FPL_POS[r.p.pos]}>{r.p.pos}{!r.p.fpl_position && <span title="Not matched to FPL yet: our position">*</span>}</span>{r.price > 0 ? ` · £${r.price.toFixed(1)}` : ''}</span>} />
				{([0, 1] as const).map((j) =>
					<td key={j} className="fpl-mark"><input type="checkbox" checked={!!owner.marks.get(r.p.player)?.[j]} aria-label={`${r.p.name}: ${j ? 'a target' : 'in my team'}`} onChange={(e) => mark(r, j, e)} /></td>)}
				<td>{pd.part_fields
					? <button type="button" className="fpl-pts" aria-expanded={open === r.p.player} title="Where the points come from" onClick={() => setOpen(open === r.p.player ? null : r.p.player)}><b>{r.xp.toFixed(1)}</b></button>
					: <b>{r.xp.toFixed(1)}</b>}</td>
				{one
					? <><td>{r.minutes}</td><td>{r.goals.toFixed(2)}</td><td>{r.assists.toFixed(2)}</td></>
					: <><td>{r.value > 0 ? r.value.toFixed(2) : '–'}</td>
						{span.map((g) => {
							const cs = r.cells.filter((c) => c.gw === g);
							return cs.length
								? <td key={g} className={`fpl-gw${cs.length > 1 ? ' double' : ''}`}>{cs.reduce((x, c) => x + c.xp, 0).toFixed(1)}<span>{cs.map((c) => oppCode(pd, c)).join(' ')}</span></td>
								: <td key={g} className="fpl-gw dim-text">–</td>;
						})}</>}
			</tr>
			{open === r.p.player && pd.part_fields && <tr className="fpl-break"><td className="fpl-parts-cell" colSpan={cols}><div className="fpl-parts">
				{partLines(pd, r, FPL_PARTS).map((x) => <div key={x.label} className="fpl-part"><span>{x.label}</span><span>{x.figure}</span><b className={x.value < 0 ? 'neg' : undefined}>{signed(x.value)}</b></div>)}
			</div></td></tr>}
		</>;
	}
}

// The model's own test results (no FPL data: points rebuilt from match stats with FPL's rules)
function Findings({ f }: { f: FindingsView }) {
	return <>
		<div className="stats-grid">
			{f.cards.map(([label, value, note]) => <div key={label} className="stats-card"><div className="stats-label">{label}</div><div className="stats-value">{value}</div><div className="stats-note">{note}</div></div>)}
		</div>
		<div className="stats-card">
			<div className="stats-label">The checks, set before testing</div>
			<div className="fpl-checks">{f.checks.map(([ok, claim, proof]) => <Fragment key={claim}><span className={`fpl-badge ${ok ? 'pass' : 'fail'}`}>{ok ? 'PASS' : 'FAIL'}</span><span><b>{claim}</b> {proof}</span></Fragment>)}</div>
		</div>
		<div className="stats-card">
			<div className="stats-label">Against simple benchmarks</div>
			<Scroll><table className="calib-table">
				<thead><tr><th>Predictor</th><th>Avg error</th><th>RMSE</th><th>Rank corr.</th><th>Top-10 hit</th><th>Top-10 pts</th></tr></thead>
				<tbody>{f.bench.map((x) => <tr key={x.name} className={x.hl ? 'fpl-hl' : undefined}><td>{x.name}</td><td>{x.mae}</td><td>{x.rmse}</td><td>{x.rank}</td><td>{x.hit}</td><td>{x.pts}</td></tr>)}</tbody></table></Scroll>
			<div className="stats-note">Average error is points per player per match (lower is better). Rank correlation: 1 = perfect ordering.
				Single-match fantasy points are mostly luck, so even a good model is often wrong about individual players.
				* v1.1 was chosen after seeing these results, so its row is not evidence: only the live test below can show it works.</div>
		</div>
		<div className="stats-card">
			<div className="stats-label">By position</div>
			<SegTable rows={f.byPosition} label="Position" />
			<Scroll><table className="calib-table u-mt10">
				<thead><tr><th>Best picks each round</th><th>Model</th><th>Last-5</th><th>PPG</th><th>No match model</th></tr></thead>
				<tbody>{f.posTop.map((x) => <tr key={x.name}><td>{x.name}</td>{x.hits.map((h, i) => <td key={i}>{h}</td>)}</tr>)}</tbody></table></Scroll>
			<div className="stats-note">Green error: the model beat the last-5 average. The match model helps most for defenders and goalkeepers, whose points depend on the opponent.</div>
		</div>
		<div className="stats-card">
			<div className="stats-label">Minutes: will he play?</div>
			<div className="vs-market">
				<span></span><span className="hd">Model</span><span className="hd">Last-5 avg</span>
				{f.minutes.map(([label, model, recent, modelBetter, recentBetter]) => <Fragment key={label}>
					<span>{label}</span><span className={`num${modelBetter ? ' better' : ''}`}>{model}</span><span className={`num${recentBetter ? ' better' : ''}`}>{recent}</span></Fragment>)}
			</div>
			<div className="stats-note">An honest miss: on plain average error the simple last-5 average is slightly better, because minutes are nearly all-or-nothing and
				a 90%-likely starter is best predicted as ~76 minutes, not 90. With injury news the model's error drops to {f.minutesWithNews} minutes.</div>
			<div className="stats-label u-mt12">Chance of starting: said vs happened</div>
			<CalibTable rows={f.startCalib} unit="Players" happened="Started" />
		</div>
		<div className="stats-card">
			<div className="stats-label">Clean sheets: said vs happened</div>
			<CalibTable rows={f.csCalib} unit="Team games" happened="Kept one" />
			<div className="stats-note">From the same goal predictions as the Matches tab. In the high-scoring 2023/24 season clean sheets were over-predicted
				(off by {f.csValidation}), so this inherits the match model's season-to-season swings.</div>
		</div>
		<div className="stats-card">
			<div className="stats-label">Why goalkeepers fail</div>
			<p className="fpl-text">Save points were tested on 2023/24 first and missed their ±10% limit for the busiest keepers
				({f.saves.pred} predicted vs {f.saves.actual} actual saves), so, as agreed in advance, they were dropped.
				Without them goalkeepers are {f.saves.without}; with them they would have been {f.saves.withThem}. v1.1 puts saves back and has to prove it on new matches.</p>
		</div>
		<div className="stats-card">
			<div className="stats-label">Through the season</div>
			<SegTable rows={f.byRound} label="Rounds" />
			<div className="stats-label u-mt12">By player level (our player rank, not FPL price)</div>
			<SegTable rows={f.byRank} label="Rank" />
		</div>
		<div className="stats-card">
			<div className="stats-label">Live test on upcoming gameweeks</div>
			<div className="stats-value">{f.live.rounds} / {f.live.target} <span className="u-sub">rounds</span></div>
			<div className="dist-row"><span className="dist-bar-wrap"><span className={`dist-bar c-blue sw-${f.live.share}`}></span></span></div>
			<div className="stats-note">
				{f.live.state === 'not_started' ? 'Not started: the snapshot table hasn\'t been created yet.'
					: f.live.state === 'waiting' || !f.live.since ? 'Ready: the first snapshots are taken before the next Premier League round.'
					: <>Capturing since <LocalTime iso={f.live.since} show="short" /> {new Date(f.live.since).getFullYear()}: {f.live.fixtures} finished matches so far.</>}
				{' '}Every player's prediction is saved before kickoff and can't be changed afterwards. Results stay sealed until
				{' '}{f.live.target} rounds are in, then the same checks are run once. This count is v1.1's; later versions' predictions are saved the same way and checked separately.</div>
		</div>
		<div className="stats-card">
			<div className="stats-label">What this doesn't show yet</div>
			<ul className="fpl-list">
				<li>No comparison with FPL's own expected points yet. FPL prices, positions and points are collected nightly from 28 Sept 2026, so this becomes possible from here on.</li>
				<li>Points are rebuilt from match stats with FPL's scoring rules, without bonus points, own goals, penalty misses or defensive-contribution points.</li>
				<li>Positions are from match data (GK/DEF/MID/FWD), which can differ from FPL's listing for some players.</li>
				<li>The match predictions used for past seasons were rebuilt afterwards, not made before kickoff.</li>
			</ul>
			<div className="stats-note">The Corner FC is not affiliated with the Premier League or Fantasy Premier League.</div>
		</div>
	</>;
}
