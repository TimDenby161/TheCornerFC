<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { columnTips, fitTable } from '#lib/actions.ts';
	import { rankTier } from '#lib/club.ts';
	import Crest from '#lib/components/Crest.svelte';
	import DualRange from '#lib/components/DualRange.svelte';
	import ExcludeChips from '#lib/components/ExcludeChips.svelte';
	import FilterMenu from '#lib/components/FilterMenu.svelte';
	import PersonChip from '#lib/components/PersonChip.svelte';
	import SubscriberLink from '#lib/components/SubscriberLink.svelte';
	import WhoPicker from '#lib/components/WhoPicker.svelte';
	import '#lib/placed.css';
	import { handlesRange, rangeText, type RangeKey } from '#lib/playerFilters.ts';
	import { pageHref } from '#lib/menu.ts';
	import type { PlayerRow } from '#lib/server/players.ts';
	import { ordinal } from '#lib/site.ts';

	let { data } = $props();

	// The page's choices as they go in the address; a default is left out.
	// (with positions picked, his rank in them takes Ability's place and is the default sort)
	const now = $derived(data.groups.length ? 'pos' : `s${data.seasons[0]}`);
	const RANGE_KEYS = ['ab', 'crank', 'mins'] as const;
	const rangeNow = (k: RangeKey) => rangeText(handlesRange(data.sliders[k].stops, data.sliders[k].a, data.sliders[k].b));
	const choices = $derived({
		...(data.filter !== 'all' ? { c: data.filter } : {}),
		...(data.excluded.length ? { ex: data.excluded.join('|') } : {}),
		...(data.search ? { q: data.search } : {}),
		...(data.sort !== now ? { sort: data.sort } : {}),
		...Object.fromEntries((['ab', 'crank', 'mins', 'age'] as const).flatMap((k) => (rangeNow(k) ? [[k, rangeNow(k)]] : []))),
		...(data.positions.length ? { pos: data.positions.join(',') } : {}),
		...(data.clubs.length ? { club: data.clubs.map((c) => c.id).join(',') } : {}),
		...(data.nats.length ? { nat: data.nats.map((n) => n.name).join('|') } : {}),
		...(data.years ? { y: '1' } : {})
	} as Record<string, string>);
	const without = (...keys: string[]) => Object.fromEntries(Object.entries(choices).filter(([k]) => !keys.includes(k)));
	const address = (q: Record<string, string>) => { const s = new URLSearchParams(q).toString(); return s ? `?${s}` : page.url.pathname; };
	// a side filter changed: the list follows, where it is on the page
	const set = (change: Record<string, string | null>) => {
		const q = { ...choices };
		for (const [k, v] of Object.entries(change)) if (v == null || v === '') delete q[k]; else q[k] = v;
		goto(address(q), { reset: false, replace: true });
	};
	const rangesOn = $derived(RANGE_KEYS.filter((k) => rangeNow(k)).length);
	// Position: each spot's button carries the picks as they would be after the press
	const posToggled = (pos: string) => (data.positions.includes(pos) ? data.positions.filter((x) => x !== pos) : [...data.positions, pos]).join(',');
	const filtersOn = $derived(rangesOn + data.excluded.length + (rangeNow('age') ? 1 : 0) + data.positions.length + data.clubs.length + data.nats.length);
	const sortHref = (key: string) => address({ ...without('sort'), ...(key === now ? {} : { sort: key }) });

	// Collapsed: Age and Ability only. Expanded (the + in the Ability heading): past seasons before
	// Ability and the projected ones after it
	const shown = $derived(data.years ? data.seasons : data.seasons.slice(0, 1));
	const future = $derived(data.years ? data.future : []);
	const short = (y: number) => `${String(y).slice(2)}/${String(y + 1).slice(2)}`;
	const seasonName = (y: number) => `${y}/${String(y + 1).slice(2)}`;
	const seasonTip = (y: number, i: number) =>
		`${i === 0 ? "Underlying Ability: the model's estimate of how good he is now (not this season's totals, which are on his page). " : ''}Rank for the ${seasonName(y)} season (the ${y} season in calendar-year leagues such as MLS and Norway${i === 0 ? '; so far' : ''}): his club's level that season, moved by how his stats compare with other players in his position (elite seasons earn extra, and positions are weighted). Squad players who play little are marked down. Every player follows the typical age curve for his position from a level of his own, and only moves off it as far as his minutes that season justify, so a thin season (an injury year, the start of a season) stays close to his curve. A season with no minutes in these leagues is estimated from his other seasons and his age, and shown outlined. Click to sort.`;

	// The rest of the rows arrive 100 at a time as the bottom of the list scrolls into view, so
	// thousands of rows are never built at once. A new list (another choice) starts again.
	// The rows added belong to the list they were asked for (its address): a new list never shows
	// another's.
	let more = $state<{ list: string; rows: PlayerRow[] }>({ list: '', rows: [] });
	const listed = $derived(page.url.search);
	const rows = $derived(more.list === listed ? [...data.rows, ...more.rows] : data.rows);
	let busy = false;
	function loadMore(sentinel: HTMLElement) {
		const box = sentinel.closest<HTMLElement>('.table-scroll')!;
		const seen = new IntersectionObserver(async (entries) => {
			if (busy || !entries.some((e) => e.isIntersecting)) return;
			busy = true;
			const key = page.url.search, at = rows.length;
			try {
				const q = new URLSearchParams(page.url.search);
				q.set('offset', String(at));
				const r = await fetch(`/players/rows?${q}`);
				if (!r.ok) return;
				const next = (await r.json()).rows as PlayerRow[];
				if (page.url.search === key && rows.length === at) more = { list: key, rows: [...(more.list === key ? more.rows : []), ...next] };
			} catch { /* the list stays as it is; scrolling again asks again */ } finally { busy = false; }
			seen.unobserve(sentinel); seen.observe(sentinel); // still in view: load again
		}, { root: getComputedStyle(box).maxHeight === 'none' ? null : box, rootMargin: '0px 0px 600px 0px' });
		seen.observe(sentinel);
		return { destroy() { seen.disconnect(); } };
	}

	let filtersOpen = $state(false);
	let typing: ReturnType<typeof setTimeout> | undefined;
	function typed(e: Event) {
		const q = (e.currentTarget as HTMLInputElement).value.trim();
		clearTimeout(typing);
		typing = setTimeout(() => goto(address({ ...without('q'), ...(q ? { q } : {}) }), { reset: false, replace: true }), 200);
	}
	// a row opens the player's page, wherever on it the click lands
	function rowClick(e: MouseEvent, id: number) {
		if ((e.target as HTMLElement).closest('a')) return;
		goto(pageHref('player', id));
	}
	const wide = $derived(!!data.search || data.filter === 'all' || !/^\d+$/.test(data.filter));
	const title = $derived(data.filter === 'all' ? 'Players' : `${data.menu.name} players`);
</script>

<svelte:head>
	<title>{title} · The Corner FC</title>
	<meta name="description" content="{data.total.toLocaleString('en-GB')} players{data.filter === 'all' ? '' : ` (${data.menu.name})`} ranked by Ability, the model's 0 to 100 estimate of how good each one is now." />
</svelte:head>

{#snippet dash()}<span class="dim">–</span>{/snippet}
{#snippet chip(v: number | null | undefined, est = false)}{#if v == null}{@render dash()}{:else if est}<span class="est"><span class="rel-chip rel-{rankTier(v)}">{Math.round(v)}</span></span>{:else}<span class="rel-chip rel-{rankTier(v)}">{Math.round(v)}</span>{/if}{/snippet}
{#snippet sortTh(key: string, cls: string, tip: string, label: string, yearsBtn = false)}
	<th class="num sortable {cls}" class:active={data.sort === key} aria-sort={data.sort === key ? (key === 'age' ? 'ascending' : 'descending') : undefined} data-tip={tip}>
		{#if yearsBtn}
			<span class="now-head"><a href={sortHref(key)} data-sveltekit-reset="false">{label}</a><a class="years-btn" role="button" href={address(data.years ? without('y', ...(/^[sf]\d/.test(data.sort) ? ['sort'] : [])) : { ...choices, y: '1' })} aria-expanded={data.years} aria-label="{data.years ? 'Hide' : 'Show'} other seasons" title="{data.years ? 'Hide' : 'Show'} past and projected seasons" data-sveltekit-reset="false">{data.years ? '−' : '+'}</a></span>
		{:else}
			<a href={sortHref(key)} data-sveltekit-reset="false">{label}</a>
		{/if}
	</th>
{/snippet}

<section class="panel" data-tab="table" data-active="true">
	<div id="table-side" class:filters-open={filtersOpen}>
		<div class="side-stick">
			<div class="more-panel" id="more-panel">
				<ExcludeChips excluded={data.excluded} action="/players" keep={without('ex', 'q')} what="player" />
				<div id="range-filter">
					<div class="pos-head"><span>Ranges</span>
						<button type="button" class="pos-clear" hidden={!rangesOn} onclick={() => set({ ab: null, crank: null, mins: null })}>Clear</button></div>
					{#each RANGE_KEYS as k (k)}
						<div class="rng-row" title={data.rangeInfo[k].tip}>
							<DualRange kind={k} name={data.rangeInfo[k].label} {...data.sliders[k]} pick={(r) => set({ [k]: r })} />
						</div>
					{/each}
				</div>
				<div id="age-filter">
					<DualRange kind="age" name="Age" {...data.sliders.age} ids={['age-min', 'age-max']} pick={(r) => set({ age: r })} />
				</div>
				<div id="pos-filter">
					<form class="contents" method="get" action="/players" data-sveltekit-reset="false">
						{#each Object.entries(without('pos', 'sort')) as [k, v] (k)}<input type="hidden" name={k} value={v} />{/each}
						<div class="pos-head"><span>Position</span>
							<button type="submit" class="pos-clear" hidden={!data.positions.length}>Clear</button></div>
						<div class="pitch">
							<svg viewBox="0 0 68 88" preserveAspectRatio="none" aria-hidden="true" fill="none" stroke="rgba(255,255,255,0.16)" stroke-width="0.6">
								<rect x="3" y="3" width="62" height="82" rx="1" /><line x1="3" y1="44" x2="65" y2="44" />
								<circle cx="34" cy="44" r="7" /><rect x="17" y="3" width="34" height="12" /><rect x="26" y="3" width="16" height="5" />
								<rect x="17" y="73" width="34" height="12" /><rect x="26" y="80" width="16" height="5" /></svg>
							{#each data.pitch as spot (spot.pos)}
								<button type="submit" name="pos" value={posToggled(spot.pos)} class="pos sx-{spot.x} sy-{spot.y}" aria-pressed={data.positions.includes(spot.pos)} title="{spot.pos}: {spot.n} players">{spot.pos}</button>
							{/each}
						</div>
					</form>
				</div>
				<WhoPicker clubs={data.clubs} nats={data.nats} pick={(clubs, nats) => set({ club: clubs.join(','), nat: nats.join('|') })} />
			</div>
			<FilterMenu id="table-filters" menu={data.menu} action="/players" keep={without('c', 'q')} />
			<button type="button" class="filter-chip" id="more-filters" aria-expanded={filtersOpen} aria-controls="more-panel" onclick={() => (filtersOpen = !filtersOpen)}>
				Filters{#if filtersOn}<span class="n">{filtersOn}</span>{/if}<span class="caret" aria-hidden="true">▾</span>
			</button>
		</div>
	</div>
	<form class="contents" method="get" action="/players" role="search" data-sveltekit-reset="false">
		{#each Object.entries(without('q')) as [k, v] (k)}<input type="hidden" name={k} value={v} />{/each}
		<input type="search" name="q" id="table-search" class="table-search" placeholder="Search players or clubs" aria-label="Search" value={data.search} oninput={typed} autocomplete="off" />
	</form>
	<div id="table-wrap" use:columnTips use:fitTable={wide}>
		{#if rows.length}
			<div class="table-scroll">
				<table class="leaderboard players" class:years={data.years}>
					<thead>
						<tr>
							<th data-tip="Position in this list, in the current sort order.">#</th>
							<th data-tip="Player, with his club's badge (click it for the club's page) and his country's flag (click it for the national team).">Player</th>
							<th class="num" data-tip="Position: the role he has started in most over his last 20 appearances.">Pos</th>
							{@render sortTh('age', 'col-age', 'Age today (sorts youngest first). Click to sort.', 'Age')}
							<th class="num col-wrank" data-tip="World rank: his place among every listed player by Ability, whatever this list is filtered or sorted by.">World</th>
							<th class="num col-lrank" data-tip="League rank: his place by Ability among the listed players in his club's league.">Lg</th>
							{@render sortTh('ga', 'col-ga', 'Goals and assists this season, all his clubs (7G 4A). Sorts by the two added together. Click to sort.', 'G/A')}
							{#each shown.map((y, i) => [y, i]).reverse() as [y, i] (y)}
								{#if i === 0 && data.groups.length}
									{@render sortTh('pos', 'col-posrank', `How good he is now as ${data.groupNames.join(' / ')}: his recent stats scored as that position against its players, with up to 6 points off for a position he hasn't played much (none once it's 40% of his starts). Only positions he has started in get a number. With several positions picked, his best of them. Click to sort.`, data.groups.length === 1 ? `As ${data.groups[0]}` : 'In pos', true)}
								{:else}
									{@render sortTh(`s${y}`, `col-season col-s${i}${i === 0 ? ' col-now' : ''}`, seasonTip(y, i), i === 0 ? 'Ability' : short(y), i === 0 && (data.future.length > 0 || data.seasons.length > 1))}
								{/if}
							{/each}
							{#each future as y, j (y)}
								{@render sortTh(`f${y}`, `col-season col-future col-f${j}`, `Projected for ${seasonName(y)}: his Ability moved along the typical age curve for his position, from his age now to his age that season (young players rise, from 31 (33 for keepers) they decline, faster each year). A guide, not a forecast of his form. Click to sort.`, short(y))}
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each rows as p, i (p.id)}
							<tr onclick={(e) => rowClick(e, p.id)}>
								<td>{i + 1}</td>
								<td><div class="pl-cell">
									{#if p.team && p.teamName}<a class="pl-badge-link" href="/club/{p.team}" title={p.teamName} aria-label={p.teamName}><Crest id={p.team} name={p.teamName} size="club-logo pl-badge" /></a>{:else}<span class="club-logo pl-badge" title="Club not known"></span>{/if}<PersonChip name={p.name} />
									<div class="pl-text">
										<div class="pl-name"><a class="player-link" href={pageHref('player', p.id)} title={p.name}><span class="pn-full">{p.name}</span><span class="pn-short">{p.short}</span></a>{#if p.nat}{#if p.flag}<a class="pl-flag" href={pageHref('nation', p.nat)} title={p.nat} aria-label="{p.nat} national team"><img class="flag" src="https://flagcdn.com/w40/{p.flag}.png" alt="" loading="lazy" /></a>{:else}<a class="nat-link" href={pageHref('nation', p.nat)}>{p.nat}</a>{/if}{/if}</div>
										<div class="pl-club">{p.teamName ?? 'Club not known'}{p.league ? ` · ${p.league}` : ''}</div>
									</div>
								</div></td>
								<td class="num">{p.pos}</td>
								<td class="num col-age">{#if p.age != null}{p.age}{:else}{@render dash()}{/if}</td>
								<td class="num col-wrank">{#if p.world != null}{p.world.toLocaleString('en-GB')}{:else}{@render dash()}{/if}</td>
								<td class="num col-lrank" title={p.lg && p.lgOf ? `${ordinal(p.lg)} of ${p.lgOf} in the ${p.league}` : undefined}>{#if p.lg != null}{p.lg}{:else}{@render dash()}{/if}</td>
								<td class="num col-ga">{#if p.ga}{p.ga[0]}G {p.ga[1]}A{:else}{@render dash()}{/if}</td>
								{#each shown.map((y, k) => [y, k]).reverse() as [y, k] (y)}
									{#if k === 0 && data.groups.length}
										<td class="num col-posrank">{@render chip(p.posRank)}</td>
									{:else}
										<td class="num col-season col-s{k}" class:col-now={k === 0}>{@render chip(p.seasons?.[k], p.estimated.includes(k))}</td>
									{/if}
								{/each}
								{#each future as y, j (y)}
									<td class="num col-season col-future col-f{j}">{@render chip(p.future?.[j])}</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
				{#if rows.length < data.total}{#key listed}<div use:loadMore></div>{/key}{/if}
			</div>
			{#if data.paywall}<div class="page-note">Player ranks outside the top 50 overall, the top 10 in each league and the top 10 in each position are for subscribers: his rank, season by season, in each position and projected. <SubscriberLink /></div>{/if}
		{:else}
			<div class="empty-state">No players match these filters.</div>
		{/if}
	</div>
</section>
