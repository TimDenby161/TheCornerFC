<script lang="ts">
	import { shortName } from '#lib/club.ts';
	import LocalTime from '#lib/components/LocalTime.svelte';
	import OwnerGate from '#lib/components/OwnerGate.svelte';
	import { CHIP_GAIN, CHIP_NAMES, FPL_POS, FPL_STATUS, type Lock } from '#lib/fantasy.ts';
	import * as Planner from '#lib/fplPlanner.js';
	import type { ChipAdvice, Move, Plan, PlanPlayer, Prep } from '#lib/fplPlanner.js';
	import { loadOwner, lockTransfers, owner } from '#lib/owner.svelte.ts';

	// The owner's FPL team with a transfer plan and chip advice, worked out here in the browser by
	// fplPlanner.js. "I've made these transfers" saves a lock for the gameweek to the owner's
	// account, and the plan then starts from the squad after them, until an FPL update reads the
	// transfers from FPL itself.
	let { data } = $props();
	$effect(() => { loadOwner(data.user?.email ?? null); });

	const t = $derived(owner.team), d = $derived(owner.fpl);
	const locks = $derived(new Map(owner.locks.filter((x) => x.season === t?.season).map((x) => [x.event_id, x])));
	// free transfers: FPL's count less any already made there, unless changed here
	let ftPicked = $state<number | null>(null);
	let busy = $state(false), msg = $state('');
	const ftFpl = $derived(t ? Math.max(t.free_transfers - t.made.length, 0) : 0);

	type Result = { prep: Prep; plan: Plan; chips: ChipAdvice[]; lock: Lock | null; ft: number };
	// null: planning; false: couldn't
	let r = $state.raw<Result | null | false>(null);
	// The search takes a moment: "Planning…" is drawn first
	$effect(() => {
		if (!t || !d) return;
		const team = t, pred = d, lock = locks.get(team.next_event) || null, ft = ftPicked ?? ftFpl;
		r = null;
		const timer = setTimeout(() => {
			try {
				const prep = Planner.prepare(pred, team);
				if (!prep) { r = false; return; }
				let first: Move[] | null = null;
				if (lock) {
					// once FPL shows transfers for the week, its squad already has them: the lock only marks the week done
					first = team.made.length ? [] : lock.transfers.map((m) => ({ out: m.out, in: m.in }));
					if (first.length && !Planner.apply(prep.ctx, prep.start, first)) first = [];
				}
				const plan = Planner.plan(prep, { ft, first });
				r = { prep, plan, chips: Planner.chipAdvice(prep, plan, team.chips, { locked: !!lock }), lock, ft };
			} catch (err) { console.error(err); r = false; }
		}, 20);
		return () => clearTimeout(timer);
	});

	const money = (tenths: number) => `£${(tenths / 10).toFixed(1)}m`;
	const passed = $derived(t ? new Date(t.next_deadline) <= new Date() : false);
	const ftNow = $derived(r ? r.ft : ftPicked ?? ftFpl);
	const P = (id: number) => (r as Result).prep.ctx.players.get(id) as PlanPlayer;
	const nm = (p: PlanPlayer) => (p.fpl ? p.name : shortName(p.name));
	const code = (id: number | string) => d?.teams[id]?.[1] || '';
	const fix = (p: PlanPlayer, k: number) => (p.fixtures[k].length ? p.fixtures[k].map((x) => (x.home ? code(x.opponent) : code(x.opponent).toLowerCase())).join(' ') : '–');
	const tag = (p: PlanPlayer) => (p.status && p.status !== 'a' ? (p.status === 'd' ? `${p.chance ?? 50}%` : FPL_STATUS[p.status] || 'Doubtful') : p.missing ? 'No prediction' : '');
	const before = (k: number) => (k === 0 ? (r as Result).prep.start : (r as Result).plan.weeks[k - 1]);
	const gainOf = (m: Move, k: number) => Planner.moveGain((r as Result).prep, before(k), m, k);
	const ORDER: Record<string, number> = { G: 0, D: 1, M: 2, F: 3 };
	// a chip's squad against the planned one: who goes, who comes
	function chipSwaps(a: ChipAdvice): [number, number][] {
		const best = a.best;
		if (!best?.squad || a.verdict === 'hold') return [];
		const from = before(best.k).squad, out = from.filter((id) => !best.squad!.includes(id)), inn = best.squad.filter((id) => !from.includes(id));
		return out.map((id, i) => [id, inn[i]]);
	}

	async function lockIn(undo: boolean) {
		if (!r || busy || !t) return;
		const res0 = r, team = t;
		const transfers = res0.plan.weeks[0].moves.map((m) => ({ out: m.out, in: m.in, out_name: P(m.out).name, in_name: P(m.in).name, sell: res0.prep.start.sell[m.out], buy: P(m.in).price }));
		busy = true; msg = '';
		const res = await lockTransfers({ undo, season: team.season, event: team.next_event, transfers: undo ? undefined : transfers });
		busy = false;
		if (!res) { msg = "Couldn't reach the database: nothing was saved."; return; }
		if (!res.ok) { msg = res.error || "Couldn't save that just now."; return; }
		const others = owner.locks.filter((x) => !(x.season === team.season && x.event_id === team.next_event));
		owner.locks = undo ? others : [...others, { season: team.season, event_id: team.next_event, transfers, locked_at: res.locked_at || new Date().toISOString() }];
	}
</script>

<svelte:head>
	<title>My FPL team · The Corner FC</title>
	<meta name="robots" content="noindex" />
</svelte:head>

{#snippet doubt(p: PlanPlayer)}{#if tag(p)}{' '}<span class="bet-tag warn">{tag(p)}</span>{/if}{/snippet}
{#snippet card(p: PlanPlayer, captain: number, vice: number)}
	<div class="mt-player"><span class="mt-nm">{nm(p)}{#if p.id === captain}{' '}<b class="mt-c" title="Captain">C</b>{:else if p.id === vice}{' '}<b class="mt-c v" title="Vice-captain">V</b>{/if}</span>
		<small>{fix(p, 0)} · {p.xp[0].toFixed(1)}</small>{@render doubt(p)}</div>
{/snippet}

<section class="panel" data-tab="myteam" data-active="true">
	<div id="myteam-body">
		{#if owner.status !== 'ok'}
			<div class="stats-card"><OwnerGate label="My FPL team" signedIn={!!data.user} /></div>
		{:else if !t}
			<div class="stats-card"><div class="stats-note">The team appears after the next FPL update.</div></div>
		{:else if !d}
			<div class="stats-card"><div class="stats-note">No predictions for the coming gameweeks yet.</div></div>
		{:else}
			<div class="stats-card mt-head">
				<div class="mt-title"><b>{t.name}</b>
					<span>GW{t.next_event} deadline <LocalTime iso={t.next_deadline} show="day" />, <LocalTime iso={t.next_deadline} show="time" />{passed ? ' · passed: the page catches up at the next FPL update' : ''}</span></div>
				<div class="mt-stats">
					<div><span class="stats-label">Bank</span><b>{money(t.bank)}</b></div>
					<div><label class="stats-label" for="mt-ft" title="Worked out from your FPL history. If FPL shows a different number, change it here.">Free transfers</label>
						<select id="mt-ft" class="mt-select" value={ftNow} onchange={(e) => { const n = +e.currentTarget.value; ftPicked = n === ftFpl ? null : n; }}>
							{#each [0, 1, 2, 3, 4, 5] as n (n)}<option value={n}>{n}</option>{/each}</select></div>
					<div><span class="stats-label">Points</span><b>{t.overall_points ?? '–'}</b></div>
					<div><span class="stats-label">Overall rank</span><b>{t.overall_rank ? t.overall_rank.toLocaleString('en-GB') : '–'}</b></div>
				</div>
			</div>
			{#if r === null}
				<div class="stats-card"><div class="stats-note">Planning…</div></div>
			{:else if !r}
				<div class="stats-card"><div class="stats-note">Couldn't plan: the predictions don't cover the next gameweek yet.</div></div>
			{:else}
				{@const w0 = r.plan.weeks[0]}
				{@const H = r.plan.weeks.length}
				{@const lu = w0.lineup}
				{@const ctx = r.prep.ctx}
				<!-- this week -->
				<div class="stats-card">
					<div class="stats-label">GW{w0.gw} transfers{r.lock ? ' · locked in' : ''}</div>
					{#if t.made.length}<div class="stats-note">Already made in FPL: {t.made.map((m) => `${m.out_name} → ${m.in_name}`).join(', ')}.</div>{/if}
					{#each w0.moves as m (m.out)}
						{@const o = P(m.out)}
						{@const i = P(m.in)}
						{@const gain = gainOf(m, 0)}
						<div class="mt-move"><span><span class="mt-nm">{nm(o)}</span> <small>{FPL_POS[o.pos]} · sell {money(before(0).sell[m.out])}</small></span>
							<span class="mt-arrow" aria-label="for">→</span>
							<span><span class="mt-nm">{nm(i)}</span> <small>{code(i.team)} · {money(i.price)}</small>{@render doubt(i)}</span>
							{#if gain != null}<b class="mt-gain" title="Expected points gained over the plan's weeks, this transfer alone">{gain >= 0 ? '+' : '−'}{Math.abs(gain).toFixed(1)}</b>{/if}</div>
					{:else}
						<p class="fpl-text">{r.lock ? 'No more transfers this week.' : `Roll the transfer: nothing gains enough over the next ${H} gameweeks. You'll have ${Math.min(Planner.MAX_FT, ftNow + 1)} free next week.`}</p>
					{/each}
					{#if w0.hits}<div class="stats-note mt-warn">Costs a {w0.hits}-point hit: worth it over the {H} gameweeks.</div>{/if}
					<div class="stats-note">Bank after: {money(w0.bank)}.</div>
					{#if r.lock}
						<div class="mt-locked"><span>✓ Locked in <LocalTime iso={r.lock.locked_at} show="day" />, <LocalTime iso={r.lock.locked_at} show="time" /></span>
							{#if !passed}<button type="button" class="filter-chip" id="mt-unlock" disabled={busy} onclick={() => lockIn(true)}>Undo</button>{/if}</div>
					{:else if !passed}
						<div class="mt-lock">
							<button type="button" class="mt-btn" id="mt-lock" disabled={busy} onclick={() => lockIn(false)}>{w0.moves.length ? "I've made these transfers" : 'Lock in: no transfers'}</button></div>
						<div class="stats-note">Made different ones? Lock in anyway: the next FPL update (07:00, 13:00 and 19:00 UTC) reads what you actually did.</div>
					{/if}
					{#if msg}<div class="stats-note mt-warn" role="alert">{msg}</div>{/if}
				</div>

				<!-- line-up for the coming gameweek -->
				<div class="stats-card">
					<div class="stats-label">GW{w0.gw} line-up · {lu.points.toFixed(1)} expected points</div>
					<div class="mt-pitch">
						{#each ['G', 'D', 'M', 'F'] as pos (pos)}
							<div class="mt-row">{#each lu.xi.map(P).filter((p) => p.pos === pos) as p (p.id)}{@render card(p, lu.captain, lu.vice)}{/each}</div>
						{/each}
					</div>
					<div class="stats-label mt-sub">Bench, in order</div>
					<div class="mt-row mt-bench">{#each lu.bench.map(P) as p (p.id)}{@render card(p, lu.captain, lu.vice)}{/each}</div>
				</div>

				<!-- the plan -->
				<div class="stats-card">
					<div class="stats-label">Plan · next {H} gameweeks</div>
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table mt-plan">
						<thead><tr><th>GW</th><th title="Free transfers that week">Free</th><th>Transfers</th><th>Hit</th><th>Captain</th><th>Pts</th></tr></thead>
						<tbody>
							{#each r.plan.weeks as w, k (w.gw)}
								<tr><td>GW{w.gw}{k === 0 && r.lock ? ' ✓' : ''}</td><td>{w.ft}</td>
									<td class="mt-plan-moves">{#each w.moves as m, j (m.out)}{#if j}<br />{/if}{nm(P(m.out))} → {nm(P(m.in))}{:else}<span class="dim-text">Roll</span>{/each}</td>
									<td>{w.hits ? `−${w.hits}` : ''}</td><td>{nm(P(w.lineup.captain))}</td><td><b>{w.points.toFixed(1)}</b></td></tr>
							{/each}
						</tbody></table></div>
					<div class="stats-note">{r.plan.total.toFixed(1)} expected points over GW{r.plan.weeks[0].gw}–{r.plan.weeks[H - 1].gw},
						{(r.plan.total - r.plan.hold).toFixed(1)} more than making no transfers. Later weeks are a sketch: each week the plan is worked out again with the latest predictions.</div>
				</div>

				<!-- chips -->
				<div class="stats-card">
					<div class="stats-label">Chips</div>
					{#each r.chips as a (a.name)}
						{@const b = a.best}
						{@const gainText = CHIP_GAIN[a.name]}
						{#if a.played != null && !a.options}
							<div class="mt-chip"><div><b>{CHIP_NAMES[a.name]}</b><span class="fpl-badge">PLAYED GW{a.played}</span></div></div>
						{:else if a.options && a.verdict === 'later' && a.window}
							<div class="mt-chip"><div><b>{CHIP_NAMES[a.name]}</b><span class="fpl-badge">FROM GW{a.window[0]}</span></div>
								<div class="stats-note">Can be played GW{a.window[0]}–{a.window[1]}: after the gameweeks predicted so far.</div></div>
						{:else if a.options && a.window}
							{@const others = a.options.filter((o) => o !== b).slice(0, 4).map((o) => `GW${o.gw} +${o.gain.toFixed(1)}`).join(' · ')}
							{@const swaps = chipSwaps(a)}
							<div class="mt-chip">
								<div><b>{CHIP_NAMES[a.name]}</b>{#if a.verdict === 'play' && b}<span class="fpl-badge pass">PLAY GW{b.gw}</span>{:else if a.verdict === 'last' && b}<span class="fpl-badge pass">LAST CHANCE: GW{b.gw}</span>{:else}<span class="fpl-badge">HOLD</span>{/if}</div>
								<div class="stats-note">
									{#if a.verdict === 'play' && b}+{b.gain.toFixed(1)} expected points {gainText}.
									{:else if a.verdict === 'last' && b}+{b.gain.toFixed(1)} expected points {gainText}: its window closes after GW{a.window[1]}, so play it in its best week left.
									{:else if b}Best week so far is GW{b.gw} at +{b.gain.toFixed(1)} {gainText}; it's worth playing from about +{Planner.CHIP_PLAY[a.name]}, usually a double gameweek. Play by GW{a.window[1]}.
									{:else}No week left for it in the predictions. Play by GW{a.window[1]}.{/if}
									{#if others}{' '}Other weeks: {others}.{/if}</div>
								{#if swaps.length}
									<details class="mt-details"><summary>The {CHIP_NAMES[a.name]} squad's changes</summary>
										{#each swaps as [out, inn] (out)}<div class="mt-move"><span class="mt-nm">{nm(P(out))}</span><span class="mt-arrow">→</span><span class="mt-nm">{nm(P(inn))}</span></div>{/each}
									</details>
								{/if}
							</div>
						{/if}
					{/each}
					<div class="stats-note">Predictions reach GW{ctx.weeks[ctx.weeks.length - 1].id}, so the advice moves as later gameweeks come into view, and double gameweeks only show once FPL schedules them. One chip a gameweek.</div>
				</div>

				<!-- squad by week -->
				<div class="stats-card">
					<div class="stats-label">Your squad · expected points</div>
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table mt-squad">
						<thead><tr><th>Player</th><th>Pos</th><th>Price</th>{#each ctx.weeks.slice(0, H) as g (g.id)}<th>GW{g.id}</th>{/each}</tr></thead>
						<tbody>
							{#each [...r.prep.start.squad].map(P).sort((x, y) => ORDER[x.pos] - ORDER[y.pos] || y.xp[0] - x.xp[0]) as p (p.id)}
								<tr><td class="mt-nm-cell"><span class="mt-nm">{nm(p)}</span>{@render doubt(p)}</td><td>{FPL_POS[p.pos]}</td>
									<td title="Selling price {money(r.prep.start.sell[p.id])}">{money(p.price)}</td>
									{#each ctx.weeks.slice(0, H) as g, k (g.id)}<td class="fpl-gw" class:double={p.fixtures[k].length > 1}>{p.fixtures[k].length ? p.xp[k].toFixed(1) : '–'}<span>{fix(p, k)}</span></td>{/each}</tr>
							{/each}
						</tbody></table></div>
				</div>

				<div class="stats-note mt-foot">
					Expected points are {d.model}'s, from the FPL tab. The plan searches the next {H} gameweeks for the transfers that add the most:
					each week it rolls the free transfer or makes one, two or three moves, and a move beyond the free ones costs 4 points.
					A squad is scored by its best line-up with the captain doubled, plus a little for the bench; each later week counts 10% less than the one before,
					and a free transfer still banked at the end is worth 1.5 points. Selling prices keep half of any rise, as FPL does.
					Squad, bank, free transfers and chips come from FPL (updated at 07:00, 13:00 and 19:00 UTC). A guide, not advice.</div>
			{/if}
		{/if}
	</div>
</section>
