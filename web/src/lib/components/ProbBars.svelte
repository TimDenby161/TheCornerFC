<script lang="ts">
	// The win-chance bars: the model's home, draw and away chances, and under it the market's
	// (the bookmakers' average with their margin removed) where its prices are known.
	// `diff` adds the gap between the two in whole points.
	let { probs, market = null, diff = false }: { probs: [number, number, number]; market?: [number, number, number] | null; diff?: boolean } = $props();
	const gap = $derived(market ? probs.map((v, i) => { const x = v - market![i]; return `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(x)}`; }) : []);
</script>

{#snippet bar([h, d, a]: [number, number, number], name: string | null, tip: string)}
	<div class="match-probs" class:labelled={!!name}>{#if name}<span class="prob-name" title={tip}>{name}</span>{/if}
		<div class="prob-bar">
			<span class="prob-home sw-{h}"></span><span class="prob-draw sw-{d}"></span><span class="prob-away sw-{a}"></span>
		</div>
		<div class="prob-labels">
			<span class="prob-home sx-0 sw-{h}">{h}%</span><span class="prob-draw sx-{h} sw-{d}">{d}%</span><span class="prob-away sx-{h + d} sw-{a}">{a}%</span>
		</div>
	</div>
{/snippet}

{#if market}
	{@render bar(probs, 'Model', "Model probability: the model's home, draw and away chances")}
	{@render bar(market, 'Market fair', 'Market fair probability: the average across bookmakers with their margin removed')}
	{#if diff}<div class="market-line" title="Model probability minus market fair probability, in percentage points. A difference is a disagreement with the market, not a betting edge or proof of value.">Difference (model − market) H <b>{gap[0]}</b> · D <b>{gap[1]}</b> · A <b>{gap[2]}</b></div>{/if}
{:else}
	{@render bar(probs, null, '')}
{/if}
