<script lang="ts">
	import Crest from './Crest.svelte';
	import LocalTime from './LocalTime.svelte';

	// A club's next match: when, who, the model's view, the predicted XI's rating, and a line on
	// availability where there is one
	type Next = { kickoff: string; live: boolean; home: boolean; opp: number; oppName: string; comp: string; win: number | null;
		gf?: number | null; ga?: number | null; proj?: string; xi?: number | null; missing?: number; status?: { cls: string; text: string } | null };
	let { n }: { n: Next } = $props();
	const proj = $derived(n.proj ?? (n.gf != null && n.ga != null ? `${n.gf.toFixed(1)}–${n.ga.toFixed(1)}` : ''));
</script>

<div class="next-card">
	<div class="next-top"><span class="next-label">{n.live ? 'Live now' : 'Next match'}</span>
		<span><LocalTime iso={n.kickoff} show="day" /> · <LocalTime iso={n.kickoff} show="time" /></span></div>
	<div class="next-opp"><Crest id={n.opp} name={n.oppName} href="/club/{n.opp}" />
		<span class="next-opp-name">{n.home ? 'v' : '@'} <a class="team-link" href="/club/{n.opp}">{n.oppName}</a></span></div>
	<div class="next-meta"><span>{n.comp}</span>{#if n.win != null}<span>{n.win}% win</span>{/if}{#if proj}<span>projected {proj}</span>{/if}
		{#if n.xi != null}<span>XI rating {Math.round(n.xi)}</span>{/if}</div>
	{#if n.missing}<div class="next-status warn">{n.missing} missing</div>{/if}
	{#if n.status}<div class="next-status {n.status.cls}">{n.status.text}</div>{/if}
</div>
