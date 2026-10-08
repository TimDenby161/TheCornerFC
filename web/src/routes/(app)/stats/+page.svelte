<script lang="ts">
	import { page } from '$app/state';
	import FilterMenu from '#lib/components/FilterMenu.svelte';
	import '#lib/placed.css';

	let { data } = $props();
	const address = (r: string) => {
		const q = new URLSearchParams({ ...(data.filter !== 'all' ? { c: data.filter } : {}), ...(r !== '30d' ? { r } : {}) }).toString();
		return q ? `?${q}` : page.url.pathname;
	};
	const s = $derived(data.stats);
</script>

<svelte:head>
	<title>{data.filter === 'all' ? 'Stats' : `${data.menu.name} stats`} · The Corner FC</title>
	<meta name="description" content="How accurate the model's match predictions have been, and how they compare with the bookmakers'." />
</svelte:head>

<section class="panel" data-tab="stats" data-active="true">
	<div id="stats-side">
		<div class="side-stick"><FilterMenu id="stats-filters" menu={data.menu} action="/stats" keep={data.range !== '30d' ? { r: data.range } : {}} /></div>
	</div>
	<div class="filter-row range-row" id="stats-ranges">
		{#each data.ranges as [key, label] (key)}<a role="button" class="filter-chip" href={address(key)} aria-pressed={data.range === key} data-sveltekit-reset="false">{label}</a>{/each}
	</div>
	<div id="stats-body">
		{#if !s}
			<div class="empty-state">No finished matches with a projection in this range.</div>
		{:else}
			<div class="stats-grid">
				{#each s.cards as [label, value, note] (label)}
					<div class="stats-card"><div class="stats-label">{label}</div><div class="stats-value">{value}</div><div class="stats-note">{note}</div></div>
				{/each}
			</div>
			{#if s.market}
				<div class="stats-card u-mb12">
					<div class="stats-label">Model vs Market ({s.market.n.toLocaleString('en-GB')} matches with odds)</div>
					<div class="vs-market">
						<span></span><span class="hd">Model</span><span class="hd">Market fair</span>
						<span>Right result</span><span class="num" class:better={s.market.right.modelBetter}>{s.market.right.model}</span><span class="num" class:better={s.market.right.marketBetter}>{s.market.right.market}</span>
						<span>Log loss</span><span class="num" class:better={s.market.ll.modelBetter}>{s.market.ll.model}</span><span class="num" class:better={s.market.ll.marketBetter}>{s.market.ll.market}</span>
					</div>
					<div class="stats-note">Market fair probability: the average across bookmakers with their margin removed, from the last odds before kickoff. Only matches with odds are compared{s.market.small ? '; the sample is still small, so treat this as a rough guide' : ''}.</div>
				</div>
				{#if s.markets.length}
					<div class="stats-card u-mb12">
						<div class="stats-label">Every bet market: Model vs Market</div>
						<table class="calib-table"><thead><tr><th>Market</th><th>Matches</th><th>Model</th><th>Market fair</th><th>Gap</th><th>Gap at opening</th></tr></thead>
							<tbody>
								{#each s.markets as m (m.label)}
									<tr><td>{m.label}</td><td>{m.n.toLocaleString('en-GB')}</td><td>{m.model}</td><td>{m.close}</td>
										<td>{#if m.gap}<span class={m.gap.cls}>{m.gap.text}</span>{/if}</td>
										<td>{#if m.open?.gap}<span class={m.open.gap.cls}>{m.open.gap.text}</span> <span class="dim">({m.open.n.toLocaleString('en-GB')})</span>{:else}<span class="dim">–</span>{/if}</td></tr>
								{/each}
							</tbody></table>
						<div class="stats-note">Log loss, lower is better, on the same matches. Gap = model minus market: green means the model was more accurate. "At opening" compares with the first prices seen, only for matches whose odds were collected before kickoff (count in brackets). Beating the opening price over many matches would be the first sign the model adds something the market lacks; a small or short-lived gap proves nothing. The goal lines come from the model's projected goals.</div>
					</div>
				{/if}
			{:else}
				<div class="stats-card u-mb12"><div class="stats-label">Model vs Market</div><div class="stats-note">No finished matches with bookmaker odds in this range yet. Odds are collected nightly for upcoming matches.</div></div>
			{/if}
			<div class="stats-card">
				<div class="stats-label">Calibration: when it says X%, how often did it happen?</div>
				<table class="calib-table">
					<thead><tr><th>Said</th><th>Calls</th><th>Avg said</th><th>Happened</th><th></th></tr></thead>
					<tbody>
						{#each s.calibration as c (c.band)}
							<tr><td>{c.band}</td><td>{c.count.toLocaleString('en-GB')}</td><td>{c.said}</td><td class={c.cls}>{c.hit}</td><td class="u-w70"><span class="calib-bar cb-{c.bar}"></span></td></tr>
						{/each}
					</tbody>
				</table>
				<div class="stats-note">Every home win, draw and away win chance counts as one call. Well calibrated means "Happened" is close to "Avg said".</div>
			</div>
			{#if s.rating}
				<div class="stats-card u-mt12">
					<div class="stats-label">Average rating</div>
					<div class="stats-value">{s.rating.avg}<span class="u-sub"> / 5 · {s.rating.label}</span></div>
					<div class="u-mt10">
						{#each s.rating.dist as d (d.r)}
							<div class="dist-row"><span class="dist-label">{d.label}</span><span class="dist-bar-wrap"><span class="dist-bar c-{d.r} sw-{d.share}"></span></span><span class="dist-pct">{d.pct}</span></div>
						{/each}
					</div>
					<div class="stats-label u-mt12">Average by factor (0–5)</div>
					<div class="u-mt4">
						{#each s.rating.factors as f (f.label)}
							<div class="dist-row"><span class="dist-label">{f.label} <span class="factor-weight">{f.weight}</span></span><span class="dist-bar-wrap"><span class="dist-bar c-blue sw-{f.share}"></span></span><span class="dist-pct">{f.value}</span></div>
						{/each}
					</div>
					<div class="stats-note">Each result is rated 1 (terrible) to 5 (excellent) from five factors, weighted as shown. Tap a result's rating on the Matches page to see its breakdown.</div>
				</div>
			{/if}
		{/if}
	</div>
</section>
