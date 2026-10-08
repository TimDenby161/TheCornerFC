<script lang="ts">
	import { shortName } from '#lib/club.ts';
	import { frozenColumns } from '#lib/actions.ts';
	import Crest from '#lib/components/Crest.svelte';
	import FantasyWho from '#lib/components/FantasyWho.svelte';
	import OwnerGate from '#lib/components/OwnerGate.svelte';
	import { codeOf, EFL_CLUB_PARTS, EFL_LEAGUE_SHORT, EFL_PARTS, EFL_SHOWN, eflClubList, eflClubRows, eflList, eflNext, eflSpan, eflSuggested, FPL_POS,
		oppCode, partLines, predRows, signed, statusTag, teamOf, versus, type ClubCell, type EflView, type FantasyPlayer, type Gameweek } from '#lib/fantasy.ts';
	import { pageHref } from '#lib/menu.ts';
	import { askKnown, loadOwner, owner } from '#lib/owner.svelte.ts';

	// Expected Fantasy EFL points for Championship, League One and League Two players and clubs.
	// Nothing comes from the Fantasy EFL site: positions are guessed from match data
	// (efl_positions.json corrects them).
	let { data } = $props();
	$effect(() => { loadOwner(data.user?.email ?? null); });

	const d = $derived(owner.efl);
	const players = $derived(d ? predRows(d) : []);
	const clubRows = $derived(d ? eflClubRows(d) : []);
	const gws = $derived(d?.gameweeks ?? []);
	const next = $derived(eflNext(gws, Date.now()));
	// gw: the gameweek on show, once the pager has moved it off the next one to start
	let v = $state<Omit<EflView, 'gw'>>({ pos: 'all', league: 'all', q: '', sort: 'xp', mode: 'gw' });
	let gwPicked = $state<number | null>(null);
	let all = $state(false), clubsAll = $state(false), open = $state<number | null>(null);
	const gw = $derived(Math.max(0, Math.min(gwPicked ?? next, gws.length - 1)));
	const view = $derived<EflView>({ ...v, gw });
	const one = $derived(v.mode === 'gw');
	const span = $derived(d && gws.length ? eflSpan(d, view, next) : []);
	// the suggested team is for the gameweek shown (the first one in the views over several)
	const g0 = $derived(one ? gws[gw] : gws[next]);
	const best = $derived(d && g0 ? eflSuggested(players, clubRows, view, g0.id) : null);
	const rows = $derived(d ? eflList(d, players, view, span) : []);
	const list = $derived(all ? rows : rows.slice(0, EFL_SHOWN));
	const clubs = $derived(d ? eflClubList(d, clubRows, view, span) : []);
	const clubList = $derived(clubsAll ? clubs : clubs.slice(0, 12));
	const cols = $derived(one ? 6 : 3 + span.length);
	$effect(() => { askKnown([...list.map((r) => r.p.player), ...(best?.xi.map((r) => r.p.player) ?? [])]); });

	const day = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
	const range = (g: Gameweek) => `${day(g.start + 'T12:00:00')} – ${day(g.end + 'T12:00:00')}`;
	const pct = (cells: ClubCell[], k: 'p_win' | 'p_clean_sheet') => cells.map((c) => `${Math.round(c[k] * 100)}%`).join(' · ');
	const clubParts = (cells: ClubCell[]) => (d?.club_part_fields || []).map((k, j) => `${EFL_CLUB_PARTS[k]} ${cells.reduce((a, c) => a + c.parts[j], 0).toFixed(2)}`).join(', ');
	const posTitle = (p: FantasyPlayer) => `${FPL_POS[p.position]}${p.corrected ? '' : ': guessed from match data'}`;
</script>

<svelte:head>
	<title>EFL Fantasy · The Corner FC</title>
	<meta name="robots" content="noindex" />
</svelte:head>

{#snippet gwCell(cs: { xp: number; opponent: number; home: boolean }[])}
	{#if cs.length}<td class="fpl-gw" class:double={cs.length > 1}>{cs.reduce((a, c) => a + c.xp, 0).toFixed(1)}<span>{d ? cs.map((c) => oppCode(d, c)).join(' ') : ''}</span></td>
	{:else}<td class="fpl-gw dim-text">–</td>{/if}
{/snippet}
{#snippet name(p: FantasyPlayer)}{#if owner.known.get(p.player)}<a class="player-link" href={pageHref('player', p.player)}>{shortName(p.name)}</a>{:else}{shortName(p.name)}{/if}{/snippet}

<section class="panel" data-tab="efl" data-active="true">
	<div id="efl-body">
		{#if owner.status !== 'ok'}
			<div class="stats-card"><OwnerGate label="Predictions" signedIn={!!data.user} why="Fantasy EFL's terms don't allow the game to be used commercially, so this is kept off the public site" /></div>
		{:else if !d || !d.players.length || !gws.length}
			<div class="stats-card"><div class="stats-note">No upcoming EFL gameweeks yet.</div></div>
		{:else}
			<div class="fpl-filters">
				{#each [['gw', 'Gameweek'], ['3', 'Next 3'], ['6', 'Next 6']] as [k, label] (k)}
					<button type="button" class="filter-chip" aria-pressed={v.mode === k} onclick={() => { v.mode = k; all = false; if (k !== 'gw') v.sort = 'xp'; }}>{label}</button>
				{/each}
				{#if one}
					<span class="fpl-pager"><button type="button" class="filter-chip" aria-label="Previous gameweek" disabled={gw === 0} onclick={() => (gwPicked = gw - 1)}>◀</button>
						<span class="fpl-span">GW{gws[gw].id} · {range(gws[gw])}</span>
						<button type="button" class="filter-chip" aria-label="Next gameweek" disabled={gw === gws.length - 1} onclick={() => (gwPicked = gw + 1)}>▶</button></span>
				{:else}
					<span class="fpl-span">GW{span[0]}–{span[span.length - 1]}</span>
				{/if}
			</div>
			<div class="fpl-filters">
				{#each [['all', 'All leagues'], ...Object.entries(d.leagues || {})] as [k, label] (k)}
					<button type="button" class="filter-chip" aria-pressed={v.league === k} onclick={() => { v.league = k; all = false; clubsAll = false; }}>{label}</button>
				{/each}
			</div>

			{#if best && g0}
				{@const cap = best.xi[0].p.player}
				{@const vice = best.xi[1].p.player}
				<div class="stats-card">
					<div class="stats-label">Suggested team · GW{g0.id} ({range(g0)}) · {(best.total + best.clubs.reduce((a, r) => a + r.xp, 0)).toFixed(1)} expected points</div>
					<div class="mt-pitch">
						{#each ['G', 'D', 'M', 'F'] as pos (pos)}
							<div class="mt-row">
								{#each best.xi.filter((r) => r.p.position === pos) as r (r.p.player)}
									{@const tag = statusTag(r.p)}
									<div class="mt-player"><span class="mt-nm">{@render name(r.p)}{#if r.p.player === cap}{' '}<b class="mt-c" title="Captain">C</b>{:else if r.p.player === vice}{' '}<b class="mt-c v" title="Vice-captain">V</b>{/if}</span>
										<small>{codeOf(d, r.p.team)} · {r.xp.toFixed(1)}</small>{#if tag}{' '}<span class="bet-tag warn" title={tag.title}>{tag.text}</span>{/if}</div>
								{/each}
							</div>
						{/each}
					</div>
					<div class="stats-label mt-sub">Clubs</div>
					<div class="mt-row mt-bench">
						{#each best.clubs as r (r.c.team)}
							<div class="mt-player"><span class="mt-nm">{teamOf(d, r.c.team)}</span>
								<small>{r.c.cells.filter((c) => c.gw === g0.id).map((c) => `v ${codeOf(d, c.opponent)} ${c.home ? 'H' : 'A'}`).join(' · ')} · {r.xp.toFixed(1)}</small></div>
						{/each}
					</div>
					<div class="stats-note">{best.formation}, at most two players from a club, captain (C) on the most expected points.
						{v.league === 'all' ? '' : `Only ${d.leagues?.[v.league]}. `}It doesn't know how many of your five picks of each club you've used.</div>
				</div>
			{/if}

			<div class="stats-card">
				<div class="stats-label">Predicted points</div>
				<div class="fpl-filters">
					{#each [['all', 'All'], ['G', 'GK'], ['D', 'DEF'], ['M', 'MID'], ['F', 'FWD']] as [k, label] (k)}
						<button type="button" class="filter-chip" aria-pressed={v.pos === k} onclick={() => { v.pos = k; all = false; }}>{label}</button>
					{/each}
					<input type="search" class="table-search fpl-search" id="efl-q" placeholder="Search players or clubs" aria-label="Search players or clubs"
						value={v.q} oninput={(e) => { v.q = e.currentTarget.value; all = false; }} />
				</div>
				<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
				<div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways">
					{#key one}
						<table class="calib-table fpl-table" class:multi={!one} use:frozenColumns>
							<thead><tr><th>#</th><th>Player</th>
								{#each (one ? [['xp', 'Pts', ''], ['minutes', 'Mins', ''], ['goals', 'G', 'Expected goals'], ['assists', 'A', 'Expected assists']] : [['xp', 'Total', '']]) as [k, label, title] (k)}
									<th title={title || undefined}><button type="button" class="fpl-sort" class:on={v.sort === k} aria-pressed={v.sort === k} aria-label={title || undefined} onclick={() => (v.sort = k as EflView['sort'])}>{label}</button></th>
								{/each}
								{#if !one}{#each span as id (id)}{@const g = gws.find((x) => x.id === id)}<th title={g ? range(g) : undefined}>GW{id}</th>{/each}{/if}
							</tr></thead>
							<tbody>
								{#each list as r, i (r.p.player)}
									<tr><td>{i + 1}</td>
										<FantasyWho id={r.p.player} name={r.p.name} team={r.p.team} teamName={teamOf(d, r.p.team)} tag={statusTag(r.p)} line={one ? versus(d, r.cells) : teamOf(d, r.p.team)}>
											{#snippet meta()}<span class="fpl-meta"><span title={posTitle(r.p)}>{r.p.position}{r.p.corrected ? '' : '*'}</span> · {EFL_LEAGUE_SHORT[r.p.league ?? 0] || ''}</span>{/snippet}
										</FantasyWho>
										<td><button type="button" class="fpl-pts" aria-expanded={open === r.p.player} title="Where the points come from" onclick={() => (open = open === r.p.player ? null : r.p.player)}><b>{r.xp.toFixed(1)}</b></button></td>
										{#if one}
											<td>{r.minutes}</td><td>{r.goals.toFixed(2)}</td><td>{r.assists.toFixed(2)}</td>
										{:else}
											{#each span as id (id)}{@render gwCell(r.cells.filter((c) => c.gw === id))}{/each}
										{/if}
									</tr>
									{#if open === r.p.player}
										<tr class="fpl-break"><td class="fpl-parts-cell" colspan={cols}><div class="fpl-parts">
											{#each partLines(d, r, EFL_PARTS, false) as x (x.label)}<div class="fpl-part"><span>{x.label}</span><span>{x.figure}</span><b class:neg={x.value < 0}>{signed(x.value)}</b></div>{/each}
										</div></td></tr>
									{/if}
								{:else}
									<tr><td colspan={cols}>No players match.</td></tr>
								{/each}
							</tbody>
						</table>
					{/key}
				</div>
				{#if rows.length > EFL_SHOWN}<button type="button" class="show-all" id="efl-more" onclick={() => (all = !all)}>{all ? 'Show fewer' : `Show all ${rows.length}`}</button>{/if}
			</div>

			<div class="stats-card">
				<div class="stats-label">Club picks</div>
				<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
				<div class="fpl-scroll" tabindex="0" role="group" aria-label="Table: scrolls sideways">
					{#key one}
						<table class="calib-table fpl-table" class:multi={!one} use:frozenColumns>
							<thead><tr><th>#</th><th>Club</th>
								{#if one}<th>Pts</th><th title="Chance of winning">Win</th><th title="Chance of a clean sheet">CS</th>
								{:else}<th>Total</th>{#each span as id (id)}<th>GW{id}</th>{/each}{/if}
							</tr></thead>
							<tbody>
								{#each clubList as r, i (r.c.team)}
									<tr><td>{i + 1}</td>
										<td class="fpl-player"><div class="fpl-who"><Crest id={r.c.team} name={teamOf(d, r.c.team)} size="efl-club-logo" />
											<div class="fpl-name"><div class="fpl-line"><span class="fpl-nm">{teamOf(d, r.c.team)}</span><span class="fpl-meta">{EFL_LEAGUE_SHORT[r.c.league ?? 0] || ''}</span></div>
											{#if one}<div class="fpl-match">{versus(d, r.cells)}</div>{/if}</div></div></td>
										{#if one}
											<td title={clubParts(r.cells)}><b>{r.xp.toFixed(1)}</b></td><td>{pct(r.cells, 'p_win')}</td><td>{pct(r.cells, 'p_clean_sheet')}</td>
										{:else}
											<td><b>{r.xp.toFixed(1)}</b></td>{#each span as id (id)}{@render gwCell(r.cells.filter((c) => c.gw === id))}{/each}
										{/if}
									</tr>
								{:else}
									<tr><td colspan="5">No clubs match.</td></tr>
								{/each}
							</tbody>
						</table>
					{/key}
				</div>
				{#if clubs.length > 12}<button type="button" class="show-all" id="efl-clubs-more" onclick={() => (clubsAll = !clubsAll)}>{clubsAll ? 'Show fewer' : `Show all ${clubs.length}`}</button>{/if}
			</div>

			<div class="stats-card"><div class="stats-note">
				Points use Fantasy EFL's scoring. Everyone: 1 for playing, 2 for 60 minutes, 3 an assist, 5 a hat-trick, −3 a missed penalty, −1 a yellow and −3 a red.
				Goals: 10 goalkeeper, 7 defender, 6 midfielder, 5 forward. Goalkeepers and defenders: 5 a clean sheet (60+ minutes), −1 per 2 conceded; goalkeepers 2 per 3 saves and 5 a penalty save.
				Defenders: 1 per 2 tackles, per 2 blocks and per 4 clearances. Midfielders: 2 an interception. Midfielders and forwards: 1 per 2 key passes and 1 a shot on target.
				Clubs: 5 a win (2 more away), 3 a draw, 2 a clean sheet, 2 for 2+ goals and 2 more for 4+.
				<br /><br />Minutes, goals, assists, penalties, clean sheets, saves and cards come from the same model as the FPL tab, run on each division's own matches and our match predictions.
				Tackles, blocks, interceptions, key passes and shots on target are each player's own rates over the last year, pulled toward his role's when he's played little.
				Our match data has no clearances, so defenders get a typical rate for their role (centre-backs 5 a match, full-backs 2.2): a rough guess. Own goals aren't included.
				<br /><br />Positions marked * are guessed from match data and may not match Fantasy EFL's; corrected ones have no mark.
				Gameweeks run Thursday to Wednesday, numbered from the season's first week, so check the numbers against the game. Predictions further ahead assume today's form and fitness.
				This is {d.model}, not yet tested against real Fantasy EFL scores: a guide, not a pick list. Click a player's points to see where they come from.</div></div>
		{/if}
	</div>
</section>
