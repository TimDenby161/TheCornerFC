<script lang="ts">
	import { page } from '$app/state';
	import '#lib/placed.css';
	import Crest from '#lib/components/Crest.svelte';
	import Flag from '#lib/components/Flag.svelte';
	import PersonChip from '#lib/components/PersonChip.svelte';
	import { pct, rankTier } from '#lib/club.ts';
	import { pageHref } from '#lib/menu.ts';

	let { data, children } = $props();

	const TABS = [['', 'Overview'], ['xi', 'Predicted XI'], ['formations', 'Formations'], ['matches', 'Matches'], ['history', 'History']];
	const base = $derived(`/club/${data.id}`);
	const tab = $derived(page.url.pathname.slice(base.length + 1).split('/')[0]);
	const signed = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)}`;
</script>

{#snippet heroRank(value: string | number, label: string, tier: number, tip: string)}
	<div class="pl-hero-rank rel-{tier}" title={tip}><span class="val">{value}</span><span class="lbl">{label}</span></div>
{/snippet}

<section class="panel" data-tab="club" data-active="true">
	<div id="club-body">
		<div class="pl-hero">
			<Crest id={data.id} name={data.name} size="club-logo-lg" />
			<div class="pl-hero-main">
				<h2>{data.name}</h2>
				{#if data.league}
					<div class="pl-hero-club"><Flag key={data.league.countryKey} name={data.league.country} /><span class="pl-league"><a class="nat-link" href={pageHref('league', data.league.id)}>{data.league.name}</a></span></div>
				{/if}
				{#if data.coach || data.rating}
					<div class="pl-hero-club pl-hero-nat">
						{#if data.coach}<PersonChip name={data.coach} size="player-photo coach-photo" /><span class="pl-meta">{data.coach}</span>{/if}
						{#if data.coach && data.rating}<span class="dim-sep">·</span>{/if}
						{#if data.rating}<a class="team-link" href="/clubs?sort=current" title="Place among every ranked club by Current Strength, as the Club Rankings are ordered. Opens the Rankings">#{data.rating.place.toLocaleString('en-GB')}</a>{/if}
					</div>
				{/if}
			</div>
			{#if data.rating}
				<div class="hero-ranks">
					{#if data.rating.form != null}{@render heroRank(signed(data.rating.form), 'Last 6', data.rating.form > 0 ? 4 : data.rating.form < 0 ? 1 : 0, "Change in Current Strength over the club's last 6 matches, in all competitions")}{/if}
					{@render heroRank(data.rating.lt, 'Baseline', data.rating.ltTier, 'Baseline Strength: the long-term level (LT ALGO), from every match since 2020')}
					{@render heroRank(data.rating.current, 'Current', data.rating.currentTier, 'Current Strength: the Elo rating after the latest match, from recent results')}
				</div>
			{/if}
		</div>

		{#if data.form.length}
			<div class="club-form lt-form"><span class="club-form-key">Form · latest first</span>{#each data.form as f, i (i)}<i class="res-{f.c.toLowerCase()}" title={f.title}>{f.c}</i>{/each}</div>
		{/if}

		{#if data.table || data.best.length}
			<div class="club-top">
				{#if data.table}
				<div class="club-mini-table">
					<div class="table-scroll"><table class="league-table">
						<thead><tr>
							<th class="cmt-head" colspan="3"><a class="cmt-link" href="{pageHref('league', data.table.league)}/table">{data.table.title}<span class="cmt-full">{' '}table</span> ›</a></th>
							<th class="lt-wdl" title="Played">P</th><th title="Goal difference">GD</th><th title="Points">Pts</th>
							<th class="lt-formcol" title="Last five league games, newest first: green won, grey drawn, red lost">Form</th>
						</tr></thead>
						<tbody>
							{#each data.table.rows as t (t.team)}
								<tr class:lt-me={t.me}>
									<td class="lt-pos {t.zone}">{t.rank}</td>
									<td class="lt-badge"><Crest id={t.team} name={t.name} href={t.me ? undefined : `/club/${t.team}`} /></td>
									<td class="lt-club lt-clubname"><span>{#if t.me}<b>{t.name}</b>{:else}<a class="team-link" href="/club/{t.team}">{t.name}</a>{/if}</span></td>
									<td class="lt-wdl">{t.played ?? ''}</td><td>{t.gd != null && t.gd > 0 ? '+' : ''}{t.gd ?? ''}</td><td><b>{t.points ?? ''}</b></td>
									<td class="lt-formcol">{#if t.form}<span class="lt-form">{#each [...t.form] as c, i (i)}<i class={c === 'W' ? 'res-w' : c === 'D' ? 'res-d' : 'res-l'}>{c}</i>{/each}</span>{/if}</td>
								</tr>
							{/each}
						</tbody>
					</table></div>
				</div>
				{/if}
				{#if data.best.length}
					<div class="club-mini-table">
						<div class="table-scroll"><table class="league-table">
							<thead><tr>
								<th class="cmt-head" colspan="2"><a class="cmt-link" href="/players?club={data.id}" title="All {data.name} players in the Players ranking">Best players<span class="cmt-full">{' · '}by Ability</span> ›</a></th>
								<th title="Underlying Ability (0-100): the model's estimate of his level"><span class="cmt-full">Ability</span><span class="cmt-short">Abil.</span></th>
								<th title="Goals this season, all his clubs">G</th><th title="Assists this season, all his clubs">A</th>
							</tr></thead>
							<tbody>
								{#each data.best as p (p.id)}
									<tr>
										<td class="lt-badge"><PersonChip name={p.name} /></td>
										<td class="lt-club"><a class="player-link" href="/player/{p.id}"><span class="cmt-full">{p.name}</span><span class="cmt-short">{p.short}</span></a>{#if p.position}{' '}<span class="bp-pos">{p.position}</span>{/if}</td>
										<td>{#if p.rank == null}–{:else}<span class="rel-chip rel-{rankTier(p.rank)}">{Math.round(p.rank)}</span>{/if}</td><td>{p.goals ?? '–'}</td><td>{p.assists ?? '–'}</td>
									</tr>
								{/each}
							</tbody>
						</table></div>
					</div>
				{/if}
			</div>
		{/if}

		{#if data.style}
			<div class="sp-grid"><div class="sp-card">
				<div class="sp-row" title="Left (blue) defensive, right (orange) attacking, grey middle balanced. Attack and Defence average to Current Strength; the lean is half their difference. The ends are the most one-sided clubs in the world. Clubs in high-scoring games drift towards attack, low-scoring ones towards defence">
					<span class="sp-lbl">Style</span>
					<span class="sp-track"><i class="sp-mid"></i><i class="sp-mark sx-{pct(data.style.x)}"></i></span>
					<span class="sp-text">{data.style.text}</span>
				</div>
			</div></div>
		{/if}

		<nav class="page-tabs" aria-label="{data.name}'s pages">
			{#each TABS as [key, label] (key)}
				<a href={key ? `${base}/${key}` : base} aria-current={tab === key ? 'page' : undefined} data-sveltekit-reset="false">{label}</a>
			{/each}
		</nav>
		<div id="club-tab">{@render children()}</div>
	</div>
</section>
