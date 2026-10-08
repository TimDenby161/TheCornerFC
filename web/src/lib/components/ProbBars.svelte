<script lang="ts">
	// The win-chance bars: the model's home, draw and away chances, and under it the market's
	// (the bookmakers' average with their margin removed) where its prices are known.
	let { probs, market = null }: { probs: [number, number, number]; market?: [number, number, number] | null } = $props();
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
{:else}
	{@render bar(probs, null, '')}
{/if}
