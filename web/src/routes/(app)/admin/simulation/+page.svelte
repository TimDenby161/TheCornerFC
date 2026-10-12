<script lang="ts">
	import { page } from '$app/state';
	import Crest from '#lib/components/Crest.svelte';
	import FilterMenu from '#lib/components/FilterMenu.svelte';
	import GamblingNote from '#lib/components/GamblingNote.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';

	let { data } = $props();
	// this page with some of its choices changed (a default is left out of the address)
	const choices = $derived({ ...(data.filter !== 'all' ? { c: data.filter } : {}), ...(data.strategy !== 'all' ? { s: data.strategy } : {}), ...(data.market !== 'all' ? { m: data.market } : {}), ...(data.view !== 'all' ? { v: data.view } : {}) } as Record<string, string>);
	const address = (change: Record<string, string>) => {
		const q = { ...choices, ...change };
		for (const k of Object.keys(q)) if (q[k] === 'all') delete q[k];
		const s = new URLSearchParams(q).toString();
		return s ? `?${s}` : page.url.pathname;
	};
	const without = (k: string) => Object.fromEntries(Object.entries(choices).filter(([x]) => x !== k));
	const STRATEGY = [['all', 'All'], ['early', 'Night before'], ['late', 'Pre-kickoff']], VIEW = [['all', 'All bets'], ['cautious', 'Cautious']];
	const MARKET = [['all', 'All markets'], ['1X2', 'Result'], ['OU15', 'O/U 1.5'], ['OU25', 'O/U 2.5'], ['OU35', 'O/U 3.5'], ['OU45', 'O/U 4.5'], ['BTTS', 'Both score']];
	type Line = { label: string; league?: number; on?: boolean; bets: number; pending: number; won: string; profit: { text: string; cls: string } | null; roi: { text: string; cls: string } | null };
</script>

<svelte:head>
	<title>Paper Simulation · The Corner FC</title>
	<meta name="description" content="A paper record of the model's selections against the bookmakers, as if each had been backed with the same stake. No real money." />
</svelte:head>

{#snippet chips(key: string, now: string, list: string[][])}{#each list as [value, label] (value)}<a role="button" class="filter-chip" href={address({ [key]: value })} aria-pressed={now === value} data-sveltekit-reset="false">{label}</a>{/each}{/snippet}
{#snippet lines(first: string, rows: Line[])}
	<table class="calib-table"><thead><tr><th>{first}</th><th>Bets</th><th>Won</th><th>Profit</th><th>Return</th></tr></thead>
		<tbody>
			{#each rows as x (x.label)}
				<tr class:u-bold={x.on}><td>{#if x.league != null}<a class="team-link" href={address({ c: x.on ? 'all' : String(x.league) })} data-sveltekit-reset="false">{x.label}</a>{:else}{x.label}{/if}</td>
					<td>{x.bets}{#if x.pending}{' '}<span class="dim">+{x.pending}</span>{/if}</td><td>{x.won}</td>
					<td>{#if x.profit}<span class={x.profit.cls}>{x.profit.text}</span>{:else}–{/if}</td><td>{#if x.roi}<span class={x.roi.cls}>{x.roi.text}</span>{:else}–{/if}</td></tr>
			{/each}
		</tbody></table>
{/snippet}

<section class="panel" data-tab="bets" data-active="true">
	<div id="bet-side">
		<div class="side-stick">{#if data.menu}<FilterMenu id="bet-filters" menu={data.menu} action="/simulation" keep={without('c')} />{/if}</div>
	</div>
	<div class="filter-row range-row" id="bet-strategy" role="group" aria-label="When the bet was taken"><span class="filter-label" aria-hidden="true">Taken</span>{@render chips('s', data.strategy, STRATEGY)}</div>
	<div class="filter-row u-mb8" id="bet-view" role="group" aria-label="Which bets"><span class="filter-label" aria-hidden="true">Bets</span>{@render chips('v', data.view, VIEW)}</div>
	<div class="filter-row u-mb10" id="bet-market" role="group" aria-label="Market"><span class="filter-label" aria-hidden="true">Market</span>{@render chips('m', data.market, MARKET)}</div>
	<div id="bets-body">
		<GamblingNote />
		{#if !data.any}
			<div class="empty-state">No simulated paper bets yet.</div>
		{:else}
			<div class="sim-banner">Simulated: paper bets only, no real money staked. Every figure here is a simulation at recorded prices. Past simulated results don't predict future results.</div>
			<div class="stats-grid">
				{#each data.cards as [label, value, note, extra] (label)}
					<div class="stats-card"><div class="stats-label">{label}</div>
						<div class="stats-value">{#if label === 'Simulated profit' && extra}<span class={extra}>{value}</span>{:else}{value}{#if label === 'Won' && extra}<span class="u-sub">{' '}{extra}</span>{/if}{/if}</div>
						<div class="stats-note">{note}</div></div>
				{/each}
			</div>
			{#if data.leagues.length}
				<div class="stats-card u-mb12"><div class="stats-label">By league</div>
					{@render lines('League', data.leagues)}
					<div class="stats-note">Tap a league to see only its bets (tap again for all). Bets = settled <span class="dim">+ pending</span>. For how accurate the predictions are in a league, pick it on the Stats page.</div></div>
			{/if}
			{#if data.markets.length}
				<div class="stats-card u-mb12"><div class="stats-label">By market</div>
					{@render lines('Market', data.markets)}
					<div class="stats-note">Paper bets, no real money: {data.stake} on every bet from a {data.bank} bank. A match gets at most one bet of each kind (result, goal line, both teams score): of several, the best is kept, judged as if the true chance were halfway between the model's and the bookmakers'. If both the night-before and pre-kickoff runs bet the same kind on a match, All counts only the night-before bet. All bets are simulated at a UK bookmaker's recorded odds. A paper bet is taken when the model's probability × that price is at least {data.minEdge}% better than even, at odds up to {data.maxOdds}: a disagreement with the market, which the results below test rather than assume. Return = profit ÷ staked. Profit needs a few hundred settled bets before it means much.</div></div>
			{/if}
			{#if data.settled.length}
				<div class="modal-section">Settled ({data.settledCount})</div>
				<div class="bets-list">
					{#each data.settled as b (b.id)}
						<div class="bet-row {b.result}">
							<div class="bet-top"><span><LocalTime iso={b.kickoff} show="day" /> <LocalTime iso={b.kickoff} show="time" /> · {b.comp}</span><span>{b.when}</span></div>
							<div class="bet-match">{b.match}{#if b.score}{' '}<span class="u-muted">({b.score})</span>{/if}</div>
							<div class="bet-pick"><span><span class="tip-badges">{#each b.teams as t (t.id)}<Crest id={t.id} name={t.name} href={b.intl ? undefined : `/club/${t.id}`} />{/each}</span>{data.stake} on {b.pick} @ <b>{b.odds}</b></span><span class={b.outcome.cls}>{b.outcome.text}</span></div>
							<div class="bet-sub">{b.sub}</div>
						</div>
					{/each}
				</div>
			{/if}
			{#if data.empty}<div class="empty-state">No bets match this filter yet.</div>{/if}
			{#if data.pending}<div class="stats-note u-mt12">{data.pending} paper bet{data.pending === 1 ? '' : 's'} still to be played: see <a href="/model-vs-market">Model vs Market</a>.</div>{/if}
		{/if}
	</div>
</section>
