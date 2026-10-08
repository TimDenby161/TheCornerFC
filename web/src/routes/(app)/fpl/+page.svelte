<script lang="ts">
	import '#lib/placed.css';
	import { frozenColumns } from '#lib/actions.ts';
	import FantasyWho from '#lib/components/FantasyWho.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';
	import OwnerGate from '#lib/components/OwnerGate.svelte';
	import { FPL_PARTS, FPL_POS, FPL_SHOWN, fplList, fplSpan, oppCode, partLines, predRows, priceLabel, priceStops, signed, statusTag, teamOf, versus,
		type FplView, type Gameweek, type ListRow, type SortKey } from '#lib/fantasy.ts';
	import { askKnown, loadOwner, markPlayer, owner } from '#lib/owner.svelte.ts';
	import { stopIndex } from '#lib/playerFilters.ts';

	let { data } = $props();
	$effect(() => { loadOwner(data.user?.email ?? null); });
	const f = $derived(data.findings);

	// ---- predictions: each player's expected points by gameweek. One gameweek at a time (◀ ▶) or
	// totals over the next 2, 5 or 10.
	let v = $state<FplView>({ pos: 'all', q: '', sort: 'xp', mode: 'gw', gw: 0, price: [null, null], mine: false, target: false });
	let all = $state(false), open = $state<number | null>(null), markMsg = $state('');
	const d = $derived(owner.fpl);
	const players = $derived(d ? predRows(d) : []);
	const gws = $derived(d?.gameweeks ?? []);
	const one = $derived(v.mode === 'gw');
	const span = $derived(d ? fplSpan(d, v) : []);
	const rows = $derived(d ? fplList(d, players, v, owner.marks) : []);
	const list = $derived(all ? rows : rows.slice(0, FPL_SHOWN));
	const cols = $derived(one ? 8 : 6 + span.length);
	$effect(() => { askKnown(list.map((r) => r.p.player)); });

	const gwLabel = (g: Gameweek) => (d?.source === 'fpl' ? `GW${g.id}` : `Round ${g.id}`);
	const day = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
	const count = (j: 0 | 1) => [...owner.marks.values()].filter((m) => m[j]).length;
	function setMode(mode: string) {
		v.mode = mode; all = false;
		if (mode !== 'gw' && (v.sort === 'minutes' || v.sort === 'goals' || v.sort === 'assists')) v.sort = 'xp';
	}
	const step = (by: number) => { v.gw = Math.max(0, Math.min(v.gw + by, gws.length - 1)); };

	// the price slider: a handle at either end leaves that end open, and the handles can't cross
	const stops = $derived(priceStops(players));
	const top = $derived(stops.length - 1);
	const a = $derived(stopIndex(stops, v.price[0], 0)), b = $derived(stopIndex(stops, v.price[1], 1));
	const at = (i: number) => Math.round((i / (top || 1)) * 100);
	function priced(end: 0 | 1, e: Event) {
		const el = e.currentTarget as HTMLInputElement;
		const lo = end === 0 ? Math.min(+el.value, b) : a, hi = end === 1 ? Math.max(+el.value, a) : b;
		el.value = String(end === 0 ? lo : hi);
		v.price = [lo === 0 ? null : stops[lo], hi === top ? null : stops[hi]];
		all = false;
	}
	async function mark(r: ListRow, which: 0 | 1, e: Event) {
		markMsg = '';
		markMsg = await markPlayer(r.p.player, which, (e.currentTarget as HTMLInputElement).checked);
	}
	const SORTS: Record<string, [SortKey, string, string][]> = {
		gw: [['xp', 'Pts', ''], ['minutes', 'Mins', ''], ['goals', 'G', 'Expected goals'], ['assists', 'A', 'Expected assists']],
		multi: [['xp', 'Total', ''], ['value', 'Pts/£m', '']]
	};
</script>

<svelte:head>
	<title>FPL · The Corner FC</title>
	<meta name="robots" content="noindex" />
</svelte:head>

{#snippet calib(rows: NonNullable<typeof f>['startCalib'], unit: string, happened: string)}
	<table class="calib-table"><thead><tr><th>Said</th><th>{unit}</th><th>{happened}</th><th></th></tr></thead><tbody>
		{#each rows as c, i (i)}<tr><td>{c.said}</td><td>{c.count}</td><td class={c.cls}>{c.hit}</td><td class="u-w70"><span class="calib-bar cb-{c.bar}"></span></td></tr>{/each}
	</tbody></table>
{/snippet}
{#snippet segTable(rows: NonNullable<typeof f>['byPosition'], label: string)}
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table">
		<thead><tr><th>{label}</th><th>Rows</th><th>Model err</th><th>Last-5 err</th><th>PPG err</th><th>Model rank</th><th>Last-5 rank</th></tr></thead>
		<tbody>{#each rows as x (x.name)}<tr><td>{x.name}</td><td>{x.rows}</td><td class={x.cls}>{x.model}</td><td>{x.recent}</td><td>{x.ppg}</td><td>{x.rank}</td><td>{x.recentRank}</td></tr>{/each}</tbody>
	</table></div>
{/snippet}

<section class="panel" data-tab="fpl" data-active="true">
	<div id="fpl-body">
		{#if owner.status !== 'ok'}
			<div class="stats-card"><OwnerGate label="Predictions" signedIn={!!data.user} /></div>
		{:else}
			{#if f}
				<details class="stats-card fpl-verdict" class:ok={f.ok}>
					<summary><span class="stats-label">Model status</span>
						<span class="fpl-verdict-line">{f.verdict}</span></summary>
					<p class="fpl-text">Our model predicts each Premier League player's fantasy points per match from expected minutes, our match predictions,
						each player's shots and chances, and clean-sheet odds. Tested on {f.testRows} player-matches since July 2024 that it had never seen,
						it beats the usual shortcuts clearly and its probabilities are well calibrated. It fails one check: goalkeepers come out too low because save points were left out.
						The predictions below use a later version (v1.4), which adds saves, injury news, bonus, cards, penalty saves and defensive contributions.
						It was designed after seeing these results, so it is now being tested on upcoming gameweeks before anyone should rely on it.</p>
				</details>
			{/if}
			<div class="stats-card" id="fpl-next">
				{#if !d || !d.players.length}
					<div class="stats-label">Predictions</div><div class="stats-note">No upcoming Premier League gameweeks yet.</div>
				{:else}
					<div class="stats-label">Predicted points</div>
					<div class="fpl-filters">
						{#each [['gw', 'Gameweek'], ['2', 'Next 2'], ['5', 'Next 5'], ['10', 'Next 10']] as [k, label] (k)}
							<button type="button" class="filter-chip" aria-pressed={v.mode === k} onclick={() => setMode(k)}>{label}</button>
						{/each}
						{#if one}
							<span class="fpl-pager"><button type="button" class="filter-chip" aria-label="Previous gameweek" disabled={v.gw === 0} onclick={() => step(-1)}>◀</button>
								<span class="fpl-span">{gwLabel(gws[v.gw])} · {day(gws[v.gw].first_kickoff)}</span>
								<button type="button" class="filter-chip" aria-label="Next gameweek" disabled={v.gw === gws.length - 1} onclick={() => step(1)}>▶</button></span>
						{:else}
							<span class="fpl-span">{gwLabel(gws[0])}–{gwLabel(gws[span.length - 1]).replace(/^\D+/, '')}</span>
						{/if}
					</div>
					<div class="fpl-filters">
						{#each [['all', 'All'], ['G', 'GK'], ['D', 'DEF'], ['M', 'MID'], ['F', 'FWD']] as [k, label] (k)}
							<button type="button" class="filter-chip" aria-pressed={v.pos === k} onclick={() => { v.pos = k; all = false; }}>{label}</button>
						{/each}
						<button type="button" class="filter-chip" aria-pressed={v.mine} onclick={() => { v.mine = !v.mine; all = false; }}>My team {count(0)}</button>
						<button type="button" class="filter-chip" aria-pressed={v.target} onclick={() => { v.target = !v.target; all = false; }}>Targets {count(1)}</button>
						<input type="search" class="table-search fpl-search" id="fpl-q" placeholder="Search players or clubs" aria-label="Search players or clubs"
							value={v.q} oninput={(e) => { v.q = e.currentTarget.value; all = false; }} />
					</div>
					{#if top >= 1}
						<div class="fpl-price" id="fpl-price">
							<div class="age-head"><span>Price</span><span class="rng-val">{priceLabel(stops, a, b)}</span></div>
							<div class="age-slider"><div class="age-track"><div class="age-fill sx-{at(a)} sr-{100 - at(b)}"></div></div>
								<input type="range" min="0" max={top} step="1" value={a} aria-label="Price: from" oninput={(e) => priced(0, e)} />
								<input type="range" min="0" max={top} step="1" value={b} aria-label="Price: to" oninput={(e) => priced(1, e)} /></div>
						</div>
					{/if}
					{#if markMsg}<div class="stats-note mt-warn" id="fpl-mark-msg" role="alert">{markMsg}</div>{/if}
					<div id="fpl-list">
						<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
						<div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways">
							{#key one}
								<table class="calib-table fpl-table" class:multi={!one} use:frozenColumns>
									<thead><tr><th>#</th><th>Player</th><th title="In my team">Mine</th><th title="A player I want">Target</th>
										{#each SORTS[one ? 'gw' : 'multi'] as [k, label, title] (k)}
											<th title={title || undefined}><button type="button" class="fpl-sort" class:on={v.sort === k} aria-pressed={v.sort === k} aria-label={title || undefined} onclick={() => (v.sort = k)}>{label}</button></th>
										{/each}
										{#if !one}{#each span as i (i)}<th title={day(gws[i].first_kickoff)}>{gwLabel(gws[i])}</th>{/each}{/if}
									</tr></thead>
									<tbody>
										{#each list as r, i (r.p.player)}
											<tr><td>{i + 1}</td>
												<FantasyWho id={r.p.player} name={r.p.name} team={r.p.team} teamName={teamOf(d, r.p.team)} tag={statusTag(r.p)}
													line={one ? versus(d, r.cells) : teamOf(d, r.p.team)}>
													{#snippet meta()}<span class="fpl-meta"><span title={FPL_POS[r.p.pos]}>{r.p.pos}{#if !r.p.fpl_position}<span title="Not matched to FPL yet: our position">*</span>{/if}</span>{r.price > 0 ? ` · £${r.price.toFixed(1)}` : ''}</span>{/snippet}
												</FantasyWho>
												{#each [0, 1] as const as j (j)}
													<td class="fpl-mark"><input type="checkbox" checked={!!owner.marks.get(r.p.player)?.[j]} aria-label="{r.p.name}: {j ? 'a target' : 'in my team'}" onchange={(e) => mark(r, j, e)} /></td>
												{/each}
												<td>{#if d.part_fields}<button type="button" class="fpl-pts" aria-expanded={open === r.p.player} title="Where the points come from" onclick={() => (open = open === r.p.player ? null : r.p.player)}><b>{r.xp.toFixed(1)}</b></button>{:else}<b>{r.xp.toFixed(1)}</b>{/if}</td>
												{#if one}
													<td>{r.minutes}</td><td>{r.goals.toFixed(2)}</td><td>{r.assists.toFixed(2)}</td>
												{:else}
													<td>{r.value > 0 ? r.value.toFixed(2) : '–'}</td>
													{#each span as g (g)}
														{@const cs = r.cells.filter((c) => c.gw === g)}
														{#if cs.length}<td class="fpl-gw" class:double={cs.length > 1}>{cs.reduce((x, c) => x + c.xp, 0).toFixed(1)}<span>{cs.map((c) => oppCode(d, c)).join(' ')}</span></td>
														{:else}<td class="fpl-gw dim-text">–</td>{/if}
													{/each}
												{/if}
											</tr>
											{#if open === r.p.player && d.part_fields}
												<tr class="fpl-break"><td class="fpl-parts-cell" colspan={cols}><div class="fpl-parts">
													{#each partLines(d, r, FPL_PARTS) as x (x.label)}<div class="fpl-part"><span>{x.label}</span><span>{x.figure}</span><b class:neg={x.value < 0}>{signed(x.value)}</b></div>{/each}
												</div></td></tr>
											{/if}
										{:else}
											<tr><td colspan={cols}>No players match.</td></tr>
										{/each}
									</tbody>
								</table>
							{/key}
						</div>
						{#if rows.length > FPL_SHOWN}<button type="button" class="show-all" id="fpl-more" onclick={() => (all = !all)}>{all ? 'Show fewer' : `Show all ${rows.length}`}</button>{/if}
					</div>
					<div class="stats-note">Points are our model's prediction with FPL's scoring rules for the player's FPL position: appearance, goals, penalties, assists, FPL assists, clean sheets,
						goals conceded, saves, penalty saves, cards, bonus and defensive contributions. Bonus is rebuilt from match stats (it tracks FPL's own closely).
						Defensive contributions combine each player's tackles, blocks and interceptions with his own FPL record this season, which also counts clearances.
						Penalties go mostly to each club's taker, from FPL's penalty order and who has taken them recently; a miss costs 2.
						FPL assists are the ones FPL gives that match stats don't: winning a penalty a teammate scores, and rebounds or deflections from a player's shot.
						Injuries use FPL's status: injured or suspended players are out until FPL's return date (or until FPL clears them), and doubtful players count at FPL's chance of playing for the next gameweek; match-day injury lists apply near kickoff.
						Click a player's points to see where they come from.
						{d.source === 'fpl' ? "Positions, prices, status and gameweeks come from FPL (updated nightly); players FPL doesn't list at their club are left out." : "FPL positions, prices and gameweeks appear after the first nightly FPL update; until then * marks our own position and rounds are the fixture list's."}
						In the multi-gameweek view, capitals are home games and lower case away; a double gameweek shows both. Predictions further ahead assume today's form and fitness.
						This is {d.model}, designed after the backtest below and still being tested on upcoming gameweeks: a guide, not a pick list.</div>
				{/if}
			</div>
			{#if !f}
				<div class="empty-state">No FPL findings yet.</div>
			{:else}
				<div class="stats-grid">
					{#each f.cards as [label, value, note] (label)}
						<div class="stats-card"><div class="stats-label">{label}</div><div class="stats-value">{value}</div><div class="stats-note">{note}</div></div>
					{/each}
				</div>
				<div class="stats-card">
					<div class="stats-label">The checks, set before testing</div>
					<div class="fpl-checks">{#each f.checks as [ok, claim, proof] (claim)}<span class="fpl-badge {ok ? 'pass' : 'fail'}">{ok ? 'PASS' : 'FAIL'}</span><span><b>{claim}</b> {proof}</span>{/each}</div>
				</div>
				<div class="stats-card">
					<div class="stats-label">Against simple benchmarks</div>
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table">
						<thead><tr><th>Predictor</th><th>Avg error</th><th>RMSE</th><th>Rank corr.</th><th>Top-10 hit</th><th>Top-10 pts</th></tr></thead>
						<tbody>{#each f.bench as x (x.name)}<tr class:fpl-hl={x.hl}><td>{x.name}</td><td>{x.mae}</td><td>{x.rmse}</td><td>{x.rank}</td><td>{x.hit}</td><td>{x.pts}</td></tr>{/each}</tbody></table></div>
					<div class="stats-note">Average error is points per player per match (lower is better). Rank correlation: 1 = perfect ordering.
						Single-match fantasy points are mostly luck, so even a good model is often wrong about individual players.
						* v1.1 was chosen after seeing these results, so its row is not evidence: only the live test below can show it works.</div>
				</div>
				<div class="stats-card">
					<div class="stats-label">By position</div>
					{@render segTable(f.byPosition, 'Position')}
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways"><table class="calib-table u-mt10">
						<thead><tr><th>Best picks each round</th><th>Model</th><th>Last-5</th><th>PPG</th><th>No match model</th></tr></thead>
						<tbody>{#each f.posTop as x (x.name)}<tr><td>{x.name}</td>{#each x.hits as h, i (i)}<td>{h}</td>{/each}</tr>{/each}</tbody></table></div>
					<div class="stats-note">Green error: the model beat the last-5 average. The match model helps most for defenders and goalkeepers, whose points depend on the opponent.</div>
				</div>
				<div class="stats-card">
					<div class="stats-label">Minutes: will he play?</div>
					<div class="vs-market">
						<span></span><span class="hd">Model</span><span class="hd">Last-5 avg</span>
						{#each f.minutes as [label, model, recent, modelBetter, recentBetter] (label)}
							<span>{label}</span><span class="num" class:better={modelBetter}>{model}</span><span class="num" class:better={recentBetter}>{recent}</span>
						{/each}
					</div>
					<div class="stats-note">An honest miss: on plain average error the simple last-5 average is slightly better, because minutes are nearly all-or-nothing and
						a 90%-likely starter is best predicted as ~76 minutes, not 90. With injury news the model's error drops to {f.minutesWithNews} minutes.</div>
					<div class="stats-label u-mt12">Chance of starting: said vs happened</div>
					{@render calib(f.startCalib, 'Players', 'Started')}
				</div>
				<div class="stats-card">
					<div class="stats-label">Clean sheets: said vs happened</div>
					{@render calib(f.csCalib, 'Team games', 'Kept one')}
					<div class="stats-note">From the same goal predictions as the Matches tab. In the high-scoring 2023/24 season clean sheets were over-predicted
						(off by {f.csValidation}), so this inherits the match model's season-to-season swings.</div>
				</div>
				<div class="stats-card">
					<div class="stats-label">Why goalkeepers fail</div>
					<p class="fpl-text">Save points were tested on 2023/24 first and missed their ±10% limit for the busiest keepers
						({f.saves.pred} predicted vs {f.saves.actual} actual saves), so, as agreed in advance, they were dropped.
						Without them goalkeepers are {f.saves.without}; with them they would have been {f.saves.withThem}. v1.1 puts saves back and has to prove it on new matches.</p>
				</div>
				<div class="stats-card">
					<div class="stats-label">Through the season</div>
					{@render segTable(f.byRound, 'Rounds')}
					<div class="stats-label u-mt12">By player level (our player rank, not FPL price)</div>
					{@render segTable(f.byRank, 'Rank')}
				</div>
				<div class="stats-card">
					<div class="stats-label">Live test on upcoming gameweeks</div>
					<div class="stats-value">{f.live.rounds} / {f.live.target} <span class="u-sub">rounds</span></div>
					<div class="dist-row"><span class="dist-bar-wrap"><span class="dist-bar c-blue sw-{f.live.share}"></span></span></div>
					<div class="stats-note">
						{#if f.live.state === 'not_started'}Not started: the snapshot table hasn't been created yet.
						{:else if f.live.state === 'waiting' || !f.live.since}Ready: the first snapshots are taken before the next Premier League round.
						{:else}Capturing since <LocalTime iso={f.live.since} show="short" /> {new Date(f.live.since).getFullYear()}: {f.live.fixtures} finished matches so far.{/if}
						Every player's prediction is saved before kickoff and can't be changed afterwards. Results stay sealed until
						{f.live.target} rounds are in, then the same checks are run once. This count is v1.1's; later versions' predictions are saved the same way and checked separately.</div>
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
				</div>
			{/if}
		{/if}
	</div>
</section>
