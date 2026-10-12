<script lang="ts">
	import Crest from '#lib/components/Crest.svelte';
	import GamblingNote from '#lib/components/GamblingNote.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';
	import MatchHead from '#lib/components/MatchHead.svelte';
	import ProbBars from '#lib/components/ProbBars.svelte';
	import '#lib/placed.css';

	let { data } = $props();
	// days and competitions fold; which are folded is the visitor's own
	let folded = $state<string[]>([]);
	const fold = (key: string) => (folded = folded.includes(key) ? folded.filter((k) => k !== key) : [...folded, key]);
	const keyed = (key: string) => (e: KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fold(key); } };
</script>

<svelte:head>
	<title>Model vs Market · The Corner FC</title>
	<meta name="description" content="Where the model and the bookmakers disagree most on upcoming matches, and how the model has done against the market so far. Paper selections only." />
</svelte:head>

<section class="panel" data-tab="tips" data-active="true">
	<div id="tips-top">
		<GamblingNote />
		<div class="tips-overview">
			{#each data.tiles as t (t.label)}
				<div class="kpi" title={t.title}><div class="kpi-head"><span class="stats-label">{t.label}</span><span class="kpi-pill" class:good={t.ok === true} class:bad={t.ok === false}>{t.pill}</span></div>
					<div class="kpi-value">{t.value}{#if t.small}<small>{t.small}</small>{/if}</div>
					<div class="kpi-rows">{#each t.rows as [k, v] (k)}<div><span>{k}</span><b>{v}</b></div>{/each}</div></div>
			{/each}
		</div>
		<div class="stats-note past-note">Past simulated results don't predict future results.</div>
	</div>
	<div id="tips-body">
		<div class="sim-banner">Model probability against market fair probability for the paper simulation's open selections. A difference is a disagreement with the market, not proven value. The price shown is a UK bookmaker's recorded price; no real money. More can appear up to 75 minutes before kickoff, after late team news.</div>
		{#each data.days as d (d.key)}
			{@const dayClosed = folded.includes(d.key)}
			<div class="tip-day" role="button" tabindex="0" aria-expanded={!dayClosed} onclick={() => fold(d.key)} onkeydown={keyed(d.key)}>
				<span class="comp-group-caret" aria-hidden="true">{dayClosed ? '▸' : '▾'}</span><span>{d.name}</span><span class="comp-group-count">{d.count}</span></div>
			<div class="tip-day-body" class:collapsed={dayClosed}>
				{#each d.comps as c (c.key)}
					{@const closed = folded.includes(c.key)}
					<div class="comp-group" class:collapsed={closed}>
						<div class="comp-group-header" role="button" tabindex="0" aria-expanded={!closed} onclick={() => fold(c.key)} onkeydown={keyed(c.key)}>
							<span class="comp-group-caret" aria-hidden="true">{closed ? '▸' : '▾'}</span><span class="comp-group-name">{c.name}</span><span class="comp-group-count">{c.count}</span></div>
						<div class="card-list">
							{#each c.matches as m (m.fixture)}
								<div class="match-card">
									{#if m.card}
										{@const card = m.card}
										<MatchHead home={card.home} away={card.away} status={card.status} hg={card.hg} ag={card.ag} homeXg={card.homeXg} awayXg={card.awayXg} likely={card.likely} source={card.source}>
											{#snippet meta()}<LocalTime iso={card.kickoff} show="time" />{card.round ? ` · ${card.round.replace(/^Regular Season - /, 'Round ')}` : ''}{/snippet}
											{#snippet right()}{#if m.picks.length > 1}<span class="match-meta">{m.picks.length} selections</span>{/if}{/snippet}
										</MatchHead>
										{#if card.probs}<ProbBars probs={card.probs} market={card.market} diff />{/if}
									{:else}
										<div class="bet-top"><span><LocalTime iso={m.kickoff} show="time" /></span>{#if m.picks.length > 1}<span class="match-meta">{m.picks.length} selections</span>{/if}</div>
										<div class="bet-match">{m.home} v {m.away}</div>
									{/if}
									<div class="tip-picks">
										{#each m.picks as p (p.id)}
											<div class="tip-pick"><span class="tip-left"><span class="tip-badges">{#each p.teams as t (t.id)}<Crest id={t.id} name={t.name} href={m.intl ? undefined : `/club/${t.id}`} />{/each}</span>
												<span><span class="sel">{p.label}</span><span class="win">{p.probs}</span></span></span><span class="odds">{p.odds}</span></div>
										{/each}
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="empty-state">No open selections right now. New ones are added the night before and shortly before kickoff.</div>
		{/each}
	</div>
</section>
