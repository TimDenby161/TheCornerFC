<script lang="ts">
	import type { Snippet } from 'svelte';
	import LocalTime from './LocalTime.svelte';
	import MatchHead from './MatchHead.svelte';
	import ProbBars from './ProbBars.svelte';
	import SubscriberLink from './SubscriberLink.svelte';
	import XiPitch from './XiPitch.svelte';
	import { cardPanels, togglePanel } from '#lib/cardPanels.svelte.ts';
	import type { Spot } from '#lib/lineups.ts';
	import type { DetailSection } from '#lib/matchDetail.ts';
	import { roundName } from '#lib/matches.ts';
	import type { CardView } from '#lib/server/matches.ts';
	import '#lib/placed.css';

	// A match: when, both sides and the score (or the projected one), the model's chances beside
	// the market's, and the key reasons. For a finished match, how the prediction did. Its
	// line-ups and the model's detail open from it, fetched when they are asked for.
	// `when`: "time" on a day's list, "day" where the list runs over many days. `lineups`: false
	// leaves the line-ups out (a club's own page). `extra` goes at the foot.
	let { m, when = 'time', lineups = true, extra }: { m: CardView; when?: 'time' | 'day'; lineups?: boolean; extra?: Snippet } = $props();
	let rating = $state(false);
	const canLineups = $derived(lineups && m.canLineups);
	const open = $derived({ lineups: cardPanels.id === m.id && cardPanels.lineups, why: cardPanels.id === m.id && cardPanels.why });

	type Side = { label: string; kit: string[] | null; ranks: boolean; spots: Spot[] | null; note: string; score: { hits: number; of: number; cls: string } | null };
	type Lineups = { locked?: boolean; sides?: Side[]; marked?: boolean; note?: string };
	type Detail = { locked?: boolean; sections?: DetailSection[]; notes?: string[] };
	type Squads = { home: Squad; away: Squad } | null;
	type Squad = { attack: number; defence: number; strength: number; recent: number | null; trend: string };
	const get = async <T,>(part: string): Promise<T | null> => { try { const r = await fetch(`/match/${m.id}/${part}`); return r.ok ? await r.json() : null; } catch { return null; } };
	// a line-up can change before kick-off, so it is asked for afresh each time it is opened; the
	// model's detail is asked for once
	let lineupsData = $state<Promise<Lineups | null> | null>(null);
	let detailData = $state<Promise<Detail | null> | null>(null);
	$effect(() => { lineupsData = open.lineups ? get<Lineups>('lineups') : null; });
	$effect(() => { if (open.why && !detailData) detailData = get<Detail>('detail'); });

	// the expected squads: once, when the card first comes into view
	let squads = $state<Squads>(null);
	function inView(node: HTMLElement) {
		if (!m.canSquads || !('IntersectionObserver' in window)) return;
		const seen = new IntersectionObserver(async (entries) => {
			if (!entries.some((e) => e.isIntersecting)) return;
			seen.disconnect();
			squads = await get<Squads>('squads');
		}, { rootMargin: '200px' });
		seen.observe(node);
		return { destroy() { seen.disconnect(); } };
	}
	// a card opens its line-ups wherever on it the click lands (not on a link or a button)
	function cardClick(e: MouseEvent) {
		if (!canLineups || (e.target as HTMLElement).closest('a, button, .fixture-lineup-panel, .why-detail, .rating-detail')) return;
		togglePanel(m.id, 'lineups');
	}
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="match-card {m.rating ? `rated acc-${m.rating.score}` : ''}" class:lineup-card={canLineups} data-fixture={m.id} onclick={cardClick} use:inView>
	<MatchHead home={m.home} away={m.away} status={m.status} hg={m.hg} ag={m.ag} penH={m.penH} penA={m.penA} homeXg={m.homeXg} awayXg={m.awayXg} likely={m.likely} source={m.source} {squads}>
		{#snippet meta()}{#if when === 'day'}<LocalTime iso={m.kickoff} show="day" /> · {/if}<LocalTime iso={m.kickoff} show="time" />{m.round ? ` · ${when === 'day' ? roundName(m.round) : m.round.replace(/^Regular Season - /, 'Round ')}` : ''}{/snippet}
		{#snippet right()}
			{#if m.rating}<button type="button" class="rating-badge badge-{m.rating.score}" title="{m.rating.score}/5 {m.rating.label}" aria-expanded={rating} onclick={() => (rating = !rating)}>{m.rating.score}/5</button>{/if}
			{#if m.tag}<span class="status-tag" class:live={m.live}>{m.tag}</span>{/if}
		{/snippet}
	</MatchHead>
	{#if m.probs}<ProbBars probs={m.probs} market={m.market} />{/if}
	{#if m.lock}
		<div class="market-line paid-lock">{m.lock === 'chances' ? "The model's chances for matches more than 7 days ahead" : `Projected score, key reasons${m.intl ? '' : ', predicted line-ups'} and model detail`} are for subscribers. <SubscriberLink /></div>
	{/if}
	{#if m.reasons.length}
		<div class="why">
			<div class="why-hd" title="The model inputs that moved this projection most, in goals of expected margin (or total goals). They describe how the model arrived at its numbers, not what will decide the match.">Key reasons</div>
			<ul class="why-list">{#each m.reasons as r (r.text)}<li><span>{r.text}</span><b>{r.size}</b></li>{/each}</ul>
		</div>
	{/if}
	{#if canLineups || m.canDetail}
		<div class="card-toggles">
			{#if canLineups}<button type="button" class="lineup-toggle" aria-expanded={open.lineups} onclick={() => togglePanel(m.id, 'lineups')}>{m.finished ? 'Line-ups' : 'Predicted line-ups'}</button>{/if}
			{#if m.canDetail}<button type="button" class="why-toggle" aria-expanded={open.why} onclick={() => togglePanel(m.id, 'why')}>{m.finished ? 'Pre-match model detail' : 'Model detail'}</button>{/if}
		</div>
	{/if}
	{#if open.lineups && lineupsData}
		<div class="fixture-lineup-panel">
			{#await lineupsData}
				<div class="empty-state">Loading {m.finished ? 'actual line-ups' : 'predicted line-ups'}…</div>
			{:then d}
				{#if !d}
					<div class="empty-state">Couldn't load the line-ups. Try again in a moment.</div>
				{:else if d.locked}
					<div class="empty-state">Predicted line-ups are for subscribers. <SubscriberLink /></div>
				{:else}
					<div class="fixture-lineups">
						{#each d.sides || [] as s (s.label)}
							<div>
								<div class="modal-section" class:xi-head={!!s.score}><span>{s.label}</span>{#if s.score}<span class="xi-score xi-score-{s.score.cls}" title="Starters the model predicted">{s.score.hits}/{s.score.of} predicted</span>{/if}</div>
								{#if s.spots}<div class="club-section pp-section"><XiPitch spots={s.spots} kit={s.kit} ranks={s.ranks} /></div>{:else}<div class="page-note">{s.note}</div>{/if}
							</div>
						{/each}
					</div>
					{#if d.marked}
						<div class="xi-legend"><span><i class="xi-key xi-hit"></i>Predicted to start</span><span><i class="xi-key xi-miss"></i>Not predicted</span>
							<span><i class="xi-key-pick">Name <b>70</b></i>The model's pick instead, with his rank going into the match</span></div>
					{/if}
					{#if d.note}<div class="page-note">{d.note}</div>{/if}
				{/if}
			{/await}
		</div>
	{/if}
	{#if open.why && detailData}
		<div class="why-detail">
			{#await detailData}
				<div class="why-note">Loading…</div>
			{:then d}
				{#if !d}
					<div class="why-note">Couldn't load the model detail. Try again in a moment.</div>
				{:else if d.locked}
					<div class="why-note">The model's detail is for subscribers. <SubscriberLink /></div>
				{:else}
					{#each d.sections || [] as sec (sec.title)}
						<div class="why-sec"><div class="why-sec-hd">{sec.title}{#if sec.unit}{' '}<span class="why-unit">{sec.unit}</span>{/if}</div>
							{#each sec.rows as r (r.label)}
								<div class="why-row" class:why-teams={r.teams} title={r.tip}><span>{r.label}</span><b>{#if typeof r.value === 'string'}{r.value}{:else}<LocalTime iso={r.value.when} show="short" /> <LocalTime iso={r.value.when} show="time" />{/if}</b></div>
							{/each}
							{#if sec.note}<div class="why-note">{sec.note}</div>{/if}
						</div>
					{/each}
					{#each d.notes || [] as n (n)}<div class="why-note">{n}</div>{/each}
				{/if}
			{/await}
		</div>
	{/if}
	{#if m.rating && rating}
		<div class="rating-detail">
			<div class="factor"><span class="factor-name">Overall</span><span class="factor-score">{m.rating.score}/5 {m.rating.label}</span></div>
			{#each m.rating.factors as f (f.label)}
				<div class="factor"><span class="factor-name">{f.label} <span class="factor-weight">{f.weight}</span></span><span class="factor-score">{f.score}/5</span></div>
			{/each}
		</div>
	{/if}
	{@render extra?.()}
</div>
