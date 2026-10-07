<script lang="ts">
	import Crest from '#lib/components/Crest.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';
	import { rankTier, shortDate, shortName } from '#lib/club.ts';
	import { OLD_SITE, pageHref } from '#lib/menu.ts';

	let { data } = $props();
	const move = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}`;
</script>

<svelte:head>
	<title>{data.name} · The Corner FC</title>
	<meta name="description" content="{data.name}: strength rating, form, league position, next fixtures with the model's chances, and recent results." />
</svelte:head>

{#if data.next}
	{@const n = data.next}
	<div class="next-card">
		<div class="next-top"><span class="next-label">{n.live ? 'Live now' : 'Next match'}</span>
			<span><LocalTime iso={n.kickoff} show="day" /> · <LocalTime iso={n.kickoff} show="time" /></span></div>
		<div class="next-opp"><Crest id={n.opp} name={n.oppName} href="/club/{n.opp}" />
			<span class="next-opp-name">{n.home ? 'v' : '@'} <a class="team-link" href="/club/{n.opp}">{n.oppName}</a></span></div>
		<div class="next-meta"><span>{n.comp}</span>{#if n.win != null}<span>{n.win}% win</span>{/if}{#if n.gf != null && n.ga != null}<span>projected {n.gf.toFixed(1)}–{n.ga.toFixed(1)}</span>{/if}
			{#if n.xi != null}<span>XI rating {Math.round(n.xi)}</span>{/if}</div>
		{#if n.missing}<div class="next-status warn">{n.missing} missing</div>{/if}
	</div>
{/if}

<div class="next-card inj-card">
	<div class="next-top"><span class="next-label">Injured &amp; Suspended</span>
		{#if data.injuries?.players.length}<span>{#if data.injuries.upcoming}Next match{:else}Latest list · {#if data.injuries.latest}{data.injuries.latest}, {/if}<LocalTime iso={data.injuries.kickoff} show="short" />{/if}</span>{/if}</div>
	{#if data.injuries?.players.length}
		{#each data.injuries.players as p (p.id)}
			<div class="inj-row">
				<div class="inj-top"><span class="inj-name" title="{p.name}: missed his club's last {p.missed} match{p.missed === 1 ? '' : 'es'}"><span class="inj-surname"><a class="player-link" href={pageHref('player', p.id)}>{shortName(p.name)}</a></span>{#if p.missed}<span class="inj-missed">&nbsp;– {p.missed}</span>{/if}</span>
					{#if p.rank != null}<span class="rel-chip rel-{rankTier(p.rank)}">{Math.round(p.rank)}</span>{:else}<span class="rel-chip rel-none" title="No rating shown">–</span>{/if}</div>
				{#if p.note === 'doubt'}<span class="inj-reason doubt">Doubtful</span>{:else if p.note === 'susp'}<span class="inj-reason susp">{p.ban ? `Suspended · ${p.ban}` : 'Suspended'}</span>{/if}
			</div>
		{/each}
	{:else}
		<div class="next-meta"><span>{data.injuries ? 'No one listed' : 'No injury list for this club'}</span></div>
	{/if}
</div>

{#if data.fixtures.length || data.results.length}
	<div class="ov-row">
		{#if data.fixtures.length}
			<div class="next-card form-card">
				<div class="next-top"><span class="next-label">Fixtures</span></div>
				<div class="next5-row next5-hdr"><span></span><span></span><span></span><span></span><span title="Projected goals">Goals</span><span title="Clean sheet chance">CS</span><span title="Win chance">Win</span></div>
				{#each data.fixtures as f (f.id)}
					<div class="next5-row" title="{f.home ? 'v' : '@'} {f.oppName} · {f.compFull}">
						<span class="next5-date"><LocalTime iso={f.kickoff} show="short" /></span>
						<Crest id={f.opp} name={f.oppName} href="/club/{f.opp}" label={f.oppName} />
						<span class="form-ha">{f.home ? 'H' : 'A'}</span>
						<Crest id={f.league} name={f.comp} league size="next5-comp" href={pageHref('league', f.league)} label={f.comp} />
						<span class="next5-num">{f.gf != null ? f.gf.toFixed(1) : ''}</span>
						<span class="next5-num">{f.cs != null ? `${f.cs}%` : ''}</span>
						<span class="next5-num strong">{f.win != null ? `${f.win}%` : ''}</span>
					</div>
				{/each}
			</div>
		{/if}
		{#if data.results.length}
			<div class="next-card form-card">
				<div class="next-top"><span class="next-label">Recent results</span></div>
				<div class="form-row form-hdr"><span></span><span></span><span></span><span></span><span>xG</span><span title="How far each result moved Current Strength">Elo ±</span></div>
				{#each data.results as r (r.date + r.opp)}
					<div class="form-row" title={r.title}>
						<span class="rel-chip rel-{r.gf > r.ga ? 4 : r.gf === r.ga ? 3 : 1}">{r.gf}–{r.ga}</span>
						<Crest id={r.opp} name={r.oppName} href="/club/{r.opp}" label={r.oppName} />
						<span class="form-ha">{r.where}</span>
						<Crest id={r.league} name={r.comp} league size="next5-comp" href={pageHref('league', r.league)} label={r.comp} />
						<span class="form-xg" class:est={r.est} title={r.est ? 'Expected goals estimated from shots: for – against' : 'Expected goals: for – against'}>{r.xgf != null && r.xga != null ? `${r.est ? '≈' : ''}${r.xgf.toFixed(1)}–${r.xga.toFixed(1)}` : '–'}</span>
						<span class="form-move">{#if r.move != null}<span class={r.move > 0 ? 'form-up' : r.move < 0 ? 'form-down' : ''}>{move(r.move)}</span>{/if}</span>
					</div>
				{/each}
			</div>
		{/if}
	</div>
{/if}
<div class="page-note">Longer-term rating history is on the History tab. The squad by position is on <a href="{OLD_SITE}#/club/{data.id}">this club's page on the current site</a> until it is rebuilt here.</div>
