<script lang="ts">
	import PersonChip from '#lib/components/PersonChip.svelte';
	import { formationDots, longDate, pct, shortDate } from '#lib/club.ts';

	let { data } = $props();
</script>

<svelte:head>
	<title>{data.name} formations · The Corner FC</title>
	<meta name="description" content="The formations {data.name} have used this season and under their manager, with the record in each." />
</svelte:head>

{#if !data.any}
	<div class="empty-state">No line-ups for this club (formations come from the leagues with match-by-match player data).</div>
{:else}
	{#if data.coach}
		<div class="next-card coach-card">
			<PersonChip name={data.coach.name} size="coach-photo" />
			<div><div class="next-label">Manager</div><div class="coach-name">{data.coach.name}</div>
				<div class="next-meta">{#if data.coach.since}<span>Since {data.coach.since}</span>{/if}{#if data.coach.matches}<span>{data.coach.matches} matches · {data.coach.record}</span>{/if}</div></div>
		</div>
	{/if}
	{#each data.sections as s (s.title)}
		<div class="club-section"><div class="modal-section">{s.title}</div>
			{#if s.used.length}
				<div class="fm-grid">
					{#each s.used as f, i (f.formation)}
						<div class="fm-card" class:top={i === 0}>
							<svg class="fm-pitch" viewBox="0 0 60 80" aria-hidden="true">
								<rect x="1" y="1" width="58" height="78" rx="3" class="fm-bg" />
								<g class="fm-lines"><line x1="1" y1="40" x2="59" y2="40" /><circle cx="30" cy="40" r="6" /><rect x="16" y="1" width="28" height="10" /><rect x="16" y="69" width="28" height="10" /></g>
								{#each formationDots(f.formation) as [x, y], k (k)}<circle cx={x.toFixed(1)} cy={y.toFixed(1)} r="3.2" class={k ? 'fm-dot' : 'fm-gk'} />{/each}
							</svg>
							<div class="fm-main"><div class="fm-name">{f.formation}</div>
								<div class="fm-count">{f.matches} match{f.matches === 1 ? '' : 'es'} · {f.share < 1 ? '<1' : Math.round(f.share)}%</div>
								<div class="fm-bar"><span class="sw-{pct(f.share)}"></span></div>
								<div class="fm-sub">{f.record} · {f.gf}–{f.ga}</div>
								<div class="fm-sub">last {f.last.slice(0, 4) === data.thisYear ? shortDate(f.last) : longDate(f.last)}</div></div>
						</div>
					{/each}
				</div>
				{#if s.missing}<div class="page-note">{s.missing} match{s.missing === 1 ? '' : 'es'} with no known line-up not counted.</div>{/if}
			{:else}
				<div class="page-note">No line-ups yet.</div>
			{/if}
		</div>
	{/each}
{/if}
