<script lang="ts">
	import PersonChip from '#lib/components/PersonChip.svelte';
	import { formationDots, longDate, pct, shortDate } from '#lib/club.ts';

	let { data } = $props();
</script>

<svelte:head>
	<title>{data.name} formations · The Corner FC</title>
	<meta name="description" content="The formations {data.name} have used under their head coach, and each starting XI match by match." />
</svelte:head>

{#if !data.any}
	<div class="empty-state">No line-ups for {data.name} yet (they come from API-Football's international matches).</div>
{:else}
	{#if data.coach}
		<div class="next-card coach-card"><PersonChip name={data.coach.name} size="coach-photo" />
			<div><div class="next-label">Head coach</div><div class="coach-name">{data.coach.name}</div>
				<div class="next-meta"><span>{data.coach.when}</span><span>{data.coach.record}</span></div></div></div>
	{/if}
	<div class="club-section"><div class="modal-section">Formations · {data.label}</div>
		{#if data.used.length}
			<div class="fm-grid">
				{#each data.used as f, i (f.formation)}
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
		{:else}
			<div class="page-note">No formations known for these matches.</div>
		{/if}
		{#if data.missing}<div class="page-note">{data.missing} match{data.missing === 1 ? '' : 'es'} with no known line-up not counted.</div>{/if}
	</div>
	<div class="club-section"><div class="modal-section">Match by match</div>
		{#each data.matches as m (m.key)}
			<details class="nat-match"><summary class="team-row">
				<span class="team-row-date">{m.date}</span>
				<span class="team-row-opp">{#if m.flag}<img class="flag" src="https://flagcdn.com/w40/{m.flag}.png" alt="" loading="lazy" />{/if}{' '}<a class="nat-link" href="/nation/{encodeURIComponent(m.opp)}">{m.opp}</a>
					<span class="club-sub u-inline" title={m.venueName}>{m.venue} · {m.tournament}</span></span>
				<span class="rel-chip rel-{m.gf > m.ga ? 4 : m.gf === m.ga ? 3 : 1}">{m.gf}–{m.ga}</span>
				<span class="nat-fm">{m.formation || '–'}</span></summary>
				{#if m.xi.length}
					<div class="nat-xi">{#each m.xi as a (a.id)}<span><span class="nat-xi-role">{a.role}</span>{#if a.link}<a class="player-link" href="/player/{a.id}">{a.name}</a>{:else}{a.name}{/if}{#if a.goals}{' '}<span class="nat-xi-goals" title="{a.goals} goal{a.goals === 1 ? '' : 's'}">{'⚽'.repeat(Math.min(a.goals, 4))}</span>{/if}</span>{/each}</div>
				{:else}
					<div class="page-note">No starting XI for this match.</div>
				{/if}
			</details>
		{/each}
	</div>
	<div class="page-note">{data.note}</div>
{/if}
