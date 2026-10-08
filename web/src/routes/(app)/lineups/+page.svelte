<script lang="ts">
	import { page } from '$app/state';
	import FilterMenu from '#lib/components/FilterMenu.svelte';
	import '#lib/placed.css';

	let { data } = $props();
	// this page with some of its choices changed (a default is left out; the number listed starts again)
	const address = (o: { src?: string; r?: string; c?: string; n?: number }) => {
		const src = o.src ?? (data.live ? 'live' : 'history'), r = o.r ?? data.range, c = o.c ?? data.filter;
		const q = new URLSearchParams({ ...(c !== 'all' ? { c } : {}), ...(src !== 'live' ? { src } : {}), ...(r !== 'all' ? { r } : {}), ...(o.n ? { n: String(o.n) } : {}) }).toString();
		return q ? `?${q}` : page.url.pathname;
	};
	const keep = $derived({ ...(data.live ? {} : { src: 'history' }), ...(data.range !== 'all' ? { r: data.range } : {}) } as Record<string, string>);
	type ClubRow = { id: number; name: string; href: string; n: number; named: string; perfect: string };
	type Tally = { id: number; name: string; team: string; n: number }[];
</script>

<svelte:head>
	<title>Line-up record · The Corner FC</title>
	<meta name="description" content="How often the line-ups the model predicted matched the team sheets: starters named, perfect XIs, by competition and club." />
</svelte:head>

{#snippet bar(label: string, share: number, tip: string, text: string, dim = '')}
	<div class="dist-row" title={tip}><span class="dist-label">{label}</span><span class="dist-bar-wrap"><span class="dist-bar c-blue sw-{share}"></span></span><span class="dist-pct">{text}{#if dim}{' '}<span class="dim">({dim})</span>{/if}</span></div>
{/snippet}
{#snippet clubTable(rows: ClubRow[])}
	<table class="calib-table"><thead><tr><th>Club</th><th>Line-ups</th><th>Named</th><th>Perfect</th></tr></thead>
		<tbody>{#each rows as c (c.id)}<tr><td><a class="team-link" href={c.href}>{c.name}</a></td><td>{c.n}</td><td>{c.named}</td><td>{c.perfect}</td></tr>{/each}</tbody></table>
{/snippet}
{#snippet playerTable(label: string, items: Tally)}
	<div class="stats-label u-mt10">{label}</div>
	{#if items.length}
		<table class="calib-table"><thead><tr><th>Player</th><th>Club</th><th>Times</th></tr></thead>
			<tbody>{#each items as p (p.id)}<tr><td><a class="player-link" href="/player/{p.id}">{p.name}</a></td><td>{p.team}</td><td>{p.n}</td></tr>{/each}</tbody></table>
	{:else}
		<div class="stats-note">No player more than once yet.</div>
	{/if}
{/snippet}

<section class="panel" data-tab="lineups" data-active="true">
	<div id="lineup-side">
		<div class="side-stick">{#if data.menu}<FilterMenu id="lineup-filters" menu={data.menu} action="/lineups" {keep} />{/if}</div>
	</div>
	<div class="filter-row range-row" id="lineup-source">
		<a role="button" class="filter-chip" href={address({ src: 'live', c: 'all' })} aria-pressed={data.live} title="Predictions saved before the team sheet came out" data-sveltekit-reset="false">Saved before kick-off</a>
		<a role="button" class="filter-chip" href={address({ src: 'history', c: 'all' })} aria-pressed={!data.live} title="The model re-run on every past match" data-sveltekit-reset="false">Reconstructed history</a>
	</div>
	<div class="filter-row range-row" id="lineup-ranges">
		{#each data.ranges as [key, label] (key)}<a role="button" class="filter-chip" href={address({ r: key })} aria-pressed={data.range === key} data-sveltekit-reset="false">{label}</a>{/each}
	</div>
	<div id="lineup-body">
		{#if data.state === 'waiting'}
			<div class="empty-state">The {data.live ? 'line-up record' : 'reconstructed history'} is built by the nightly data run. Check back tomorrow.</div>
		{:else if data.state === 'none'}
			<div class="empty-state">No scored line-ups in this range.</div>
		{:else if data.state === 'empty'}
			<div class="empty-state">No line-ups scored yet. Each needs a prediction saved before the team sheet came out, and the official XI afterwards.</div>
		{:else if data.state === 'ok'}
			{#if !data.live}
				<div class="stats-card u-mb12"><div class="stats-note"><b>Reconstructed, not a live record.</b> Today's model re-run on every past match, picking from what it knew before kick-off: the last five matches' minutes and formations, and the injury list. It can't know late team news, and older matches were never predicted this way at the time, so read it as how the current model does on past matches. The live record (Saved before kick-off) is the one that counts.</div></div>
			{/if}
			<div class="stats-grid">
				{#each data.cards as [label, value, note] (label)}<div class="stats-card"><div class="stats-label">{label}</div><div class="stats-value">{value}</div><div class="stats-note">{note}</div></div>{/each}
			</div>
			{#if data.sample}<div class="stats-card u-mb12"><div class="stats-note">{data.sample}</div></div>{/if}

			<div class="stats-card"><div class="stats-label">Starters named correctly, per line-up</div>
				<div class="u-mt6">{#each data.spread as b (b.label)}{@render bar(b.label, b.share, b.tip, b.text)}{/each}</div>
				<div class="stats-note">Number of team line-ups, and their share, by how many of the 11 starters the predicted XI named.</div></div>
			<div class="stats-card"><div class="stats-label">Over time: average named correctly each {data.step}</div>
				<div class="u-mt6">{#each data.trend as t (t.label)}{@render bar(t.label, t.share, t.tip, t.value, String(t.n))}{/each}</div>
				<div class="stats-note">Out of 11, newest first; the number of line-ups is in brackets.</div></div>
			<div class="stats-card"><div class="stats-label">By position</div>
				<table class="calib-table"><thead><tr><th>Line</th><th>Starters</th><th>Predicted</th><th>Hit rate</th><th></th></tr></thead>
					<tbody>{#each data.lines as l (l.name)}<tr><td>{l.name}</td><td>{l.starters.toLocaleString('en-GB')}</td><td>{l.hit.toLocaleString('en-GB')}</td><td>{l.rate}</td><td class="u-w70"><span class="calib-bar cb-{l.bar}"></span></td></tr>{/each}</tbody></table>
				<div class="stats-note">Of the players who started in each part of the pitch, how many were in the predicted XI. Lines come from the team sheet.</div></div>
			{#if data.live}
				<div class="stats-card"><div class="stats-label">How far before kick-off</div>
					<table class="calib-table"><thead><tr><th>Saved</th><th>Line-ups</th><th>Named</th><th>Perfect</th></tr></thead>
						<tbody>{#each data.timing as t (t.label)}<tr><td>{t.label}</td><td>{t.n}</td><td>{t.named}</td><td>{t.perfect}</td></tr>{/each}</tbody></table>
					<div class="stats-note">The prediction scored is the last one saved before the team sheet came out.</div></div>
			{/if}
			<div class="stats-card"><div class="stats-label">By competition</div>
				<table class="calib-table"><thead><tr><th>Competition</th><th>Line-ups</th><th>Named</th><th>Perfect</th><th>Position</th></tr></thead>
					<tbody>{#each data.comps as c (c.id)}<tr class:u-bold={c.on}><td><a class="team-link" href={address({ c: String(c.id) })} data-sveltekit-reset="false">{c.name}</a></td><td>{c.n}</td><td>{c.named}</td><td>{c.perfect}</td><td>{c.position}</td></tr>{/each}</tbody></table>
				<div class="stats-note">Tap a competition to narrow to it.</div></div>
			<div class="stats-card"><div class="stats-label">By club</div>
				{#if data.clubs.easiest && data.clubs.hardest}
					<div class="stats-label u-mt8">Easiest to predict</div>{@render clubTable(data.clubs.easiest)}
					<div class="stats-label u-mt12">Hardest to predict</div>{@render clubTable(data.clubs.hardest)}
				{:else}
					<div class="stats-note">The easiest and hardest clubs are listed once enough clubs have {data.clubMin} or more line-ups scored.</div>
				{/if}
				<details><summary>All {data.clubs.all.length} clubs</summary>{@render clubTable(data.clubs.all)}</details>
				<div class="stats-note">Clubs with at least {data.clubMin} line-ups scored in the easiest and hardest lists.</div></div>
			<div class="stats-card"><div class="stats-label">Players the model got wrong most often</div>
				{@render playerTable('Started, but not in the predicted XI', data.missed)}
				{@render playerTable("In the predicted XI, but didn't start", data.wrong)}
				<div class="stats-note">{data.missedTotal.toLocaleString('en-GB')} starters missed in all; each miss is one wrong pick in their place.</div></div>
			{#if data.live}
				<div class="stats-card"><div class="stats-label">By model version</div>
					<table class="calib-table"><thead><tr><th>Version</th><th>Line-ups</th><th>Named</th><th>Perfect</th></tr></thead>
						<tbody>{#each data.versions as v (v.label)}<tr><td>{v.label} <span class="lr-sub">{v.name}{v.from ? ` · from ${v.from}` : ''}</span></td><td>{v.n}</td><td>{v.named}</td><td>{v.perfect}</td></tr>{/each}</tbody></table>
					<div class="stats-note">A new version starts whenever the line-up code changes, even if the name stays the same. Each keeps its own record.</div></div>
			{/if}
			<div class="stats-card"><div class="stats-label">Every line-up</div>
				<table class="calib-table lr-list"><thead><tr><th>Date</th><th>Line-up</th><th>Right</th><th>Missed</th></tr></thead>
					<tbody>
						{#each data.rows as r, i (i)}
							<tr><td>{r.date}</td>
								<td><a class="team-link" href={r.href}>{r.team}</a> {r.home ? 'v' : 'at'} {r.opponent}<span class="lr-sub">{r.comp}</span></td>
								<td><span class="xi-score xi-score-{r.correct >= 9 ? 'good' : r.correct >= 7 ? 'ok' : 'poor'}">{r.correct}/11</span></td><td>{r.missed || '–'}</td></tr>
						{/each}
					</tbody></table>
				{#if data.more}<a role="button" class="filter-chip lr-more" href={address({ n: data.more.n })} data-sveltekit-reset="false">Show more ({data.more.left.toLocaleString('en-GB')} left)</a>{/if}
				<div class="stats-note">Newest first.{data.live ? " A match's Line-ups on the Matches page shows the XIs side by side for the last three weeks." : ''}{data.excluded ? ` ${data.excluded} line-ups aren't counted because no complete official XI was recorded.` : ''}</div></div>
		{/if}
	</div>
</section>
