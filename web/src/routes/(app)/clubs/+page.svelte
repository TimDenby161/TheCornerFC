<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { columnTips, fitTable } from '#lib/actions.ts';
	import Crest from '#lib/components/Crest.svelte';
	import ExcludeChips from '#lib/components/ExcludeChips.svelte';
	import FilterMenu from '#lib/components/FilterMenu.svelte';
	import Flag from '#lib/components/Flag.svelte';
	import Move from '#lib/components/Move.svelte';
	import { pageHref } from '#lib/menu.ts';
	import { ordinal } from '#lib/site.ts';
	import type { Sort } from '#lib/rankings.ts';

	let { data } = $props();

	const COLUMNS: { key: Sort; cls: string; tip: string }[] = [
		{ key: 'lt', cls: '', tip: 'Baseline Strength: the long-term Elo rating (LT ALGO), a smoothed rating weighted mostly to the average over the last 100 matches. Slow to move, and the better guide for matches months away.' },
		{ key: 'trend', cls: 'col-gap', tip: 'Gap: Current Strength minus Baseline Strength. Green: rated above its long-term level; red: below it. A difference in level, not recent movement (see Last 6).' },
		{ key: 'current', cls: '', tip: 'Current Strength: the Elo rating after the latest match. 100 points is worth a goal a game. It rises when a club does better than expected against that opponent, and falls when it does worse. Colour: green is the top 5% of all clubs, amber the top 20%, orange the top half, red the rest.' },
		{ key: 'form', cls: 'col-recent', tip: "Recent movement: how much the club's Elo rating has changed over its last 6 matches." }
	];
	const LABELS: Record<Sort, string> = { lt: 'Baseline', trend: 'Gap', current: 'Current', form: 'Last 6' };

	// The page's choices as they go in the address; a default is left out.
	const choices = $derived({
		...(data.filter !== 'all' ? { c: data.filter } : {}),
		...(data.excluded.length ? { ex: data.excluded.join('|') } : {}),
		...(data.search ? { q: data.search } : {}),
		...(data.sort !== 'current' ? { sort: data.sort } : {})
	} as Record<string, string>);
	const without = (...keys: string[]) => Object.fromEntries(Object.entries(choices).filter(([k]) => !keys.includes(k)));
	const address = (q: Record<string, string>) => { const s = new URLSearchParams(q).toString(); return s ? `?${s}` : page.url.pathname; };

	const ex = $derived(new Set(data.excluded));
	let filtersOpen = $state(false);

	// the search narrows the list as it is typed
	let typing: ReturnType<typeof setTimeout> | undefined;
	function typed(e: Event) {
		const q = (e.currentTarget as HTMLInputElement).value.trim();
		clearTimeout(typing);
		typing = setTimeout(() => goto(address({ ...without('q'), ...(q ? { q } : {}) }), { reset: false, replace: true }), 200);
	}
	// a row opens its club's page, wherever on it the click lands
	function rowClick(e: MouseEvent, team: number) {
		if ((e.target as HTMLElement).closest('a')) return;
		goto(pageHref('club', team));
	}
	const showMeta = $derived(!!data.search || data.wide);
	const title = $derived(data.filter === 'all' ? 'Clubs' : `${data.menu.name} clubs`);
</script>

<svelte:head>
	<title>{title} · The Corner FC</title>
	<meta name="description" content="Strength ratings for {data.rows.length.toLocaleString('en-GB')} clubs{data.filter === 'all' ? '' : ` (${data.menu.name})`} on one scale: long-term level, current rating and recent movement." />
</svelte:head>

<section class="panel" data-tab="table" data-active="true">
	<div id="table-side" class:filters-open={filtersOpen}>
		<div class="side-stick">
			<div class="more-panel" id="more-panel">
				<ExcludeChips excluded={data.excluded} action="/clubs" keep={without('ex', 'q')} />
			</div>
			<FilterMenu id="table-filters" menu={data.menu} action="/clubs" keep={without('c', 'q')} />
			<button type="button" class="filter-chip" id="more-filters" aria-expanded={filtersOpen} aria-controls="more-panel" onclick={() => (filtersOpen = !filtersOpen)}>
				Exclude{#if ex.size}<span class="n">{ex.size}</span>{/if}<span class="caret" aria-hidden="true">▾</span>
			</button>
		</div>
	</div>
	<form class="contents" method="get" action="/clubs" role="search" data-sveltekit-reset="false">
		{#each Object.entries(without('q')) as [k, v] (k)}<input type="hidden" name={k} value={v} />{/each}
		<input type="search" name="q" id="table-search" class="table-search" placeholder="Search clubs, leagues or countries" aria-label="Search" value={data.search} oninput={typed} autocomplete="off" />
	</form>
	<div id="table-wrap" use:columnTips use:fitTable={showMeta}>
		{#if data.rows.length}
			<div class="table-scroll">
				<table class="leaderboard clubs">
					<thead>
						<tr>
							<th data-tip="Position in this list, in the current sort order.">#</th>
							<th data-tip="Club badge. Click a club to open its page."><span class="th-club">Club</span></th>
							<th data-tip="Club name, with its country and league. Click a club to open its page.">Club</th>
							<th class="num col-spare" data-tip="World rank: place among every ranked club by Baseline Strength, whatever this list is filtered or sorted by.">World</th>
							<th class="num col-dom" data-tip="In league: place by Baseline Strength among the clubs in its league this season. TheCornerFC's ranking, not the league table (that's on the competition's page).">In lg</th>
							{#each COLUMNS as col (col.key)}
								<th class="num sortable {col.cls}" class:active={data.sort === col.key} aria-sort={data.sort === col.key ? 'descending' : undefined} data-tip="{col.tip} Click to sort.">
									<a href={address({ ...without('sort'), ...(col.key === 'current' ? {} : { sort: col.key }) })} data-sveltekit-reset="false">{#if col.key === 'lt'}<span class="th-full">Baseline</span><span class="th-short">Base</span>{:else}{LABELS[col.key]}{/if}</a>
								</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each data.rows as r, i (r.team)}
							<tr onclick={(e) => rowClick(e, r.team)}>
								<td>{i + 1}</td>
								<td><Crest id={r.team} name={r.name} /></td>
								<td>
									<div class="club-cell">
										<a class="team-link" href={pageHref('club', r.team)} data-short={r.short}>{r.name}</a>
										{#if showMeta && r.country}
											<span class="club-meta"><Flag key={r.countryKey} name={r.country} /><span class="cm-league"><a class="nat-link" href={pageHref('league', r.league)}>{r.leagueName}</a></span></span>
										{/if}
									</div>
								</td>
								<td class="num col-spare">{r.place.world.toLocaleString('en-GB')}</td>
								<td class="num col-dom u-muted" title={r.place.dom ? `${ordinal(r.place.dom)} of ${r.place.domOf} in the ${r.leagueName} by Baseline Strength` : undefined}>{r.place.dom ?? ''}</td>
								<td class="num"><span class="rel-chip rel-{r.ltTier}">{r.lt}</span></td>
								<td class="num col-gap"><Move value={r.trend} /></td>
								<td class="num"><span class="rel-chip rel-{r.currentTier}">{r.current}</span></td>
								<td class="num col-recent"><Move value={r.form} /></td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{:else}
			<div class="empty-state">No clubs {data.excluded.length ? 'match these filters' : 'found'}.</div>
		{/if}
	</div>
</section>
