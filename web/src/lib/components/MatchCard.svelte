<script lang="ts">
	import type { Snippet } from 'svelte';
	import LocalTime from './LocalTime.svelte';
	import MatchHead from './MatchHead.svelte';
	import ProbBars from './ProbBars.svelte';
	import SubscriberLink from './SubscriberLink.svelte';
	import { roundName } from '#lib/matches.ts';
	import type { CardView } from '#lib/server/matches.ts';
	import '#lib/placed.css';

	// A match: when, both sides and the score (or the projected one), the model's chances beside
	// the market's, and the key reasons. For a finished match, how the prediction did.
	// `when`: "time" on a day's list, "day" where the list runs over many days. `extra` goes at
	// the foot (a club's page adds the competition and its win chance).
	let { m, when = 'time', extra }: { m: CardView; when?: 'time' | 'day'; extra?: Snippet } = $props();
	let detail = $state(false);
</script>

<div class="match-card {m.rating ? `rated acc-${m.rating.score}` : ''}" data-fixture={m.id}>
	<MatchHead home={m.home} away={m.away} status={m.status} hg={m.hg} ag={m.ag} penH={m.penH} penA={m.penA} homeXg={m.homeXg} awayXg={m.awayXg} likely={m.likely} source={m.source}>
		{#snippet meta()}{#if when === 'day'}<LocalTime iso={m.kickoff} show="day" /> · {/if}<LocalTime iso={m.kickoff} show="time" />{m.round ? ` · ${when === 'day' ? roundName(m.round) : m.round.replace(/^Regular Season - /, 'Round ')}` : ''}{/snippet}
		{#snippet right()}
			{#if m.rating}<button type="button" class="rating-badge badge-{m.rating.score}" title="{m.rating.score}/5 {m.rating.label}" aria-expanded={detail} onclick={() => (detail = !detail)}>{m.rating.score}/5</button>{/if}
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
	{#if m.rating && detail}
		<div class="rating-detail">
			<div class="factor"><span class="factor-name">Overall</span><span class="factor-score">{m.rating.score}/5 {m.rating.label}</span></div>
			{#each m.rating.factors as f (f.label)}
				<div class="factor"><span class="factor-name">{f.label} <span class="factor-weight">{f.weight}</span></span><span class="factor-score">{f.score}/5</span></div>
			{/each}
		</div>
	{/if}
	{@render extra?.()}
</div>
