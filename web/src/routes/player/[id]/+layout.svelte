<script lang="ts">
	import { page } from '$app/state';
	import '#lib/placed.css';
	import Crest from '#lib/components/Crest.svelte';
	import PersonChip from '#lib/components/PersonChip.svelte';
	import { rankTier } from '#lib/club.ts';
	import { pageHref } from '#lib/menu.ts';

	let { data, children } = $props();

	const TABS = [['', 'Overview'], ['stats', 'Stats'], ['matches', 'Matches'], ['career', 'Career']];
	const base = $derived(`/player/${data.id}`);
	const tab = $derived(page.url.pathname.slice(base.length + 1).split('/')[0]);
	const ABILITY_TIP = "Underlying Ability (0-100): the model's estimate of his level, from his clubs' strength, his stats against players in his position and his age curve. It carries over from earlier seasons, so it isn't a measure of current form: Current Season and Recent Performance are shown separately";
	const gaTip = $derived(`League ${data.seasonName}, all his clubs`);
	// his league place's colour: the top 2% green, 10% amber, 35% orange, the rest red
	const placeTier = (place: number, of: number) => { const s = place / Math.max(1, of); return s <= 0.02 ? 4 : s <= 0.1 ? 3 : s <= 0.35 ? 2 : 1; };
	const now = $derived(data.now);
</script>

{#snippet kf(label: string, value: string, sub: string, tip: string, tier: number | null = null)}
	<div class="kf-tile {tier ? `kf-t${tier}` : ''}" title={tip}><div class="kf-label">{label}</div><div class="kf-value">{value}</div>{#if sub}<div class="kf-sub">{sub}</div>{/if}</div>
{/snippet}
{#snippet icons(n: number, icon: string, word: string)}{#if n}<span class="ga-icon" title="{n} {word}{n === 1 ? '' : 's'}">{n > 3 ? `${icon}×${n}` : icon.repeat(n)}</span>{/if}{/snippet}

<section class="panel" data-tab="club" data-active="true">
	<div id="club-body">
		<div class="pl-hero">
			<PersonChip name={data.name} size="player-photo-lg" />
			<div class="pl-hero-main">
				<h2>{data.name}</h2>
				<div class="pl-hero-club">{#if data.team}<Crest id={data.team.id} name={data.team.name} href="/club/{data.team.id}" />{/if}
					<span>{#if data.team}<a class="team-link" href="/club/{data.team.id}">{data.team.name}</a>{:else}<span class="dim-text">club not known</span>{/if}{#if data.league}<span class="dim-sep">{' · '}</span><a class="pl-league team-link" href={pageHref('league', data.league.id)}>{data.league.name}</a>{/if}</span></div>
				<div class="pl-hero-club pl-hero-nat">
					{#if data.nat}{#if data.nat.flag}<img class="flag" src="https://flagcdn.com/w40/{data.nat.flag}.png" alt="" loading="lazy" />{/if}<span><a class="nat-link" href={pageHref('nation', data.nat.name)}>{data.nat.name}</a></span><span class="dim-sep">·</span>{/if}
					<span class="pl-meta">{data.position}</span>{#if data.age != null}<span class="dim-sep">·</span><span class="pl-meta" title={data.born ? `Born ${data.born}` : undefined}>{data.age}</span>{/if}
				</div>
			</div>
			<div class="hero-ranks">
				<div class="pl-hero-rank pl-hero-ga" title={gaTip}><span class="val">{now?.goals ?? (now ? 0 : '–')}</span><span class="lbl">Goals</span></div>
				<div class="pl-hero-rank pl-hero-ga" title={gaTip}><span class="val">{now?.assists ?? (now ? 0 : '–')}</span><span class="lbl">Assists</span></div>
				{#if data.rank == null}
					<div class="pl-hero-rank" title="His rank is for subscribers"><span class="val">–</span><span class="lbl">Ability</span></div>
				{:else}
					<div class="pl-hero-rank rel-{rankTier(data.rank)}" title={ABILITY_TIP}><span class="val">{data.rank}</span><span class="lbl">Ability</span></div>
				{/if}
			</div>
		</div>
		{#if data.locked}<div class="pl-callout">Player ranks outside the top 50 overall, the top 10 in each league and the top 10 in each position are for subscribers: his rank, season by season, in each position and projected.</div>{/if}

		<div class="key-figures pl-figures"><div class="kf-group"><div class="kf-tiles kf-main">
			{#if data.leagueRank && data.league}
				{@render kf('League rank', `#${data.leagueRank.place.toLocaleString('en-GB')}`, `of ${data.leagueRank.of.toLocaleString('en-GB')} in ${data.league.name}`, `Place by Ability among ranked players at ${data.league.name} clubs`, placeTier(data.leagueRank.place, data.leagueRank.of))}
			{/if}
			{@render kf(`${data.season} minutes`, now ? now.minutes!.toLocaleString('en-GB') : '–', now?.apps != null ? `${now.apps} apps${now.starts != null ? ` · ${now.starts} started` : ''}` : 'league matches', 'League minutes this season, all his clubs')}
			{@render kf(`${data.season} goals · assists`, now?.minutes ? `${now.goals ?? 0} · ${now.assists ?? 0}` : '–', now?.minutes ? 'league matches' : 'no minutes yet', 'League goals and assists this season, all his clubs')}
		</div></div></div>

		<div class="club-section pl-block">
			{#if !data.recent.apps.length}
				<div class="modal-section">Recent Performance</div>
				<div class="pl-callout">No match-by-match data for him: only the leagues with per-match player stats have it.</div>
			{:else}
				{#if data.recent.stale}
					<div class="modal-section">Most recent appearances · last played {data.recent.lastDate}</div>
					<div class="pl-callout">No league appearance for {data.recent.days} days, so these are not current form.</div>
				{/if}
				<div class="form-strip">
					{#each data.recent.apps as m, i (i)}
						<div class="form-cell" title={m.title}>
							<span class="rel-chip {m.gf > m.ga ? 'rel-4' : m.gf === m.ga ? 'rel-none' : 'rel-1'}">{m.gf}–{m.ga}</span><span class="form-ga">{@render icons(m.goals, '⚽', 'goal')}{@render icons(m.assists, '👟', 'assist')}</span>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<nav class="page-tabs" aria-label="{data.name}'s pages">
			{#each TABS as [key, label] (key)}
				<a href={key ? `${base}/${key}` : base} aria-current={tab === key ? 'page' : undefined} data-sveltekit-reset="false">{label}</a>
			{/each}
		</nav>
		<div id="pl-tab">{@render children()}</div>
	</div>
</section>
