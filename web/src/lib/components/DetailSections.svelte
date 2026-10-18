<script lang="ts">
	import LocalTime from './LocalTime.svelte';
	import type { DetailSection } from '#lib/matchDetail.ts';

	// A match's model detail, section by section (matchDetail). tips: each row's explanation
	// written out under it, where there is room (The Model's worked example), not only on hover
	let { sections, notes = [], tips = false }: { sections: DetailSection[]; notes?: string[]; tips?: boolean } = $props();
</script>

{#each sections as sec (sec.title)}
	<div class="why-sec"><div class="why-sec-hd">{sec.title}{#if sec.unit}{' '}<span class="why-unit">{sec.unit}</span>{/if}</div>
		{#each sec.rows as r (r.label)}
			<div class="why-row" class:why-teams={r.teams} title={tips ? undefined : r.tip}><span>{r.label}</span><b>{#if typeof r.value === 'string'}{r.value}{:else}<LocalTime iso={r.value.when} show="short" /> <LocalTime iso={r.value.when} show="time" />{/if}</b></div>
			{#if tips && r.tip}<div class="why-tip">{r.tip}</div>{/if}
		{/each}
		{#if sec.note}<div class="why-note">{sec.note}</div>{/if}
	</div>
{/each}
{#each notes as n (n)}<div class="why-note">{n}</div>{/each}
