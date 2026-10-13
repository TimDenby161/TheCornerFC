<script lang="ts">
	import ChangeLines from '#lib/components/ChangeLines.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';
	import { shortId } from '#lib/changes.ts';

	let { data } = $props();
	const c = $derived(data.change);
	const STAGE: Record<string, string> = { 'Deployed to production': 'deployed', 'Tested and rejected': 'rejected', 'Being tested': 'testing', Reverted: 'reverted' };
</script>

<svelte:head>
	<title>{shortId(c.id)}: {c.title} · The Corner FC</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<section class="panel mc mc-detail" data-tab="changes" data-active="true">
	<p class="mc-env">{data.environment === 'production' ? 'Production' : data.environment === 'staging' ? 'Staging: test data, not the live record' : 'Environment not named'} · {shortId(c.id)} ({c.id}) · {c.component} · {c.kind}</p>
	<h2 class="mc-title" id="mc-title">{c.title}</h2>
	<p><span class="mc-stage {STAGE[c.stage] ?? 'other'}">{c.stage}</span> <span class="mc-sub mc-inline">Status: {c.status} · proposed {c.date}{#if c.deployed_on} · deployed {c.deployed_day_known ? c.deployed_on : c.deployed_on.slice(0, 7)}{/if}</span></p>
	{#if data.ready}<div class="sim-banner mc-ready-banner">Ready to implement: a test has statistically enough evidence that this is an improvement of at least the bar. Releasing it is your decision.</div>{:else if data.why}<div class="sim-banner">Not marked ready. {data.why}.</div>{/if}
	{#if c.kind === 'experiment'}<div class="sim-banner">An experiment. Its results are tests on past or held-out matches and were never production results; nothing here was deployed.</div>{/if}
	{#if c.retrospective}<div class="sim-banner">Recorded on {c.recorded}, after the test had been run: the hypothesis and expectation below were taken from the experiment's own files, not written here beforehand.</div>{/if}
	{#if data.differs.length}<div class="sim-banner mc-alert" role="alert">The register's file no longer matches this record: {data.differs.join('; ')}</div>{/if}

	<div class="mc-cols">
		<div class="stats-card"><div class="stats-label">The change</div>
			<dl class="mc-dl"><dt>What was changed</dt><dd>{c.what}</dd><dt>Why it was proposed</dt><dd>{c.why}</dd><dt>How it works</dt><dd>{c.how}</dd>
				<dt>Code</dt><dd>Commit: {c.commit}{#if c.experiment} · <code>{c.experiment}</code>{/if} · model version: {c.version}</dd></dl></div>
		<div class="stats-card"><div class="stats-label">Expected, before testing</div>
			<dl class="mc-dl"><dt>Hypothesis</dt><dd>{c.hypothesis}</dd><dt>Expected to improve</dt><dd>{c.improves}</dd>
				<dt>Expected size</dt><dd>{#if c.expected.length}{#each c.expected as m (m.metric)}<span class="mc-line-item">{m.metric} {m.delta}{#if m.range} ({m.range}){/if}<span class="mc-sub">{m.source}</span></span>{/each}{:else}Not specified{/if}</dd>
				<dt>Effect on betting</dt><dd>{c.betting}</dd><dt>Confidence</dt><dd>{c.confidence}</dd><dt>Evidence behind it</dt><dd>{c.evidence}</dd>
				<dt>Success criteria</dt><dd>{c.criteria}</dd></dl></div>
	</div>

	<div class="stats-card" id="mc-results"><div class="stats-label">What testing showed</div>
		{#if data.results.length}
			{#each data.results as r (r.label + r.metric)}
				<div class="mc-result">
					<p class="mc-result-head"><span class="mc-pill mark-{r.mark}">{r.word} {r.delta}</span> <b>{r.label}</b> <span class="mc-sub mc-inline">{r.kind} · {r.unseen} · {r.date}</span></p>
					<table class="calib-table"><thead><tr><th>{r.metric}</th><th>Before</th><th>After</th><th>Change</th><th>Interval</th><th>Matches</th><th>Period</th></tr></thead>
						<tbody><tr><td></td><td>{r.before}</td><td>{r.after}</td><td>{r.delta}{#if r.percent} ({r.percent}){/if}</td><td>{r.interval ?? 'Not recorded'}</td><td>{r.n}</td><td>{r.period}</td></tr></tbody></table>
					<p class="stats-note"><b>Meaningful?</b> {r.meaningful} <b>Against bookmakers:</b> {r.market}. <span class="mc-sub mc-inline">Source: {r.source}</span></p>
				</div>
			{/each}
		{:else}<div class="stats-note">No result has been recorded for this change.</div>{/if}
	</div>

	{#if data.tracking}
		<div class="stats-card" id="mc-tracking"><div class="stats-label">On live matches</div>
			{#if data.tracking.why}
				<p class="stats-note"><b>{data.tracking.text}.</b> {data.tracking.why}.</p>
			{:else}
				<table class="calib-table"><thead><tr><th></th><th>Live matches</th><th>Weeks</th><th>Gain on them</th><th>Range it could still lie in</th><th>Standing</th></tr></thead>
					<tbody><tr><td>Log loss</td><td>{data.tracking.n.toLocaleString('en-GB')}</td><td>{data.tracking.weeks}</td><td>{data.tracking.gain ?? '–'}</td><td>{data.tracking.range ?? '–'}</td><td>{data.tracking.text}</td></tr></tbody></table>
				{#if data.tracking.called}<p class="stats-note"><b>{data.tracking.called}.</b> A call stands once made.</p>{/if}
				{#if data.tracking.series.length >= 2}
					<ChangeLines label="Gain on live matches by week, with its range" zero places={4} series={[
						{ name: 'Gain so far', cls: 'live', points: data.tracking.series.map((p) => ({ x: p.week, value: p.gain, note: `${p.n.toLocaleString('en-GB')} matches` })) },
						{ name: 'Range: lowest', cls: 'recon', points: data.tracking.series.map((p) => ({ x: p.week, value: p.low })) },
						{ name: 'Range: highest', cls: 'recon', points: data.tracking.series.map((p) => ({ x: p.week, value: p.high })) }]} />
				{/if}
				<p class="stats-note">Scored against the current model on every finished match since {data.tracking.start}{#if data.tracking.to} (to {data.tracking.to}){/if} that has a prediction stored before kickoff, with the setting its experiment fixed. Plus is better. The range is the kind that stays valid however often it is looked at, so it is wide; the change is proven when the whole range is on one side of zero, and nothing is called before {data.tracking.minMatches} matches and {data.tracking.minWeeks} weeks. Updated <LocalTime iso={data.tracking.generated} show="short" />.</p>
			{/if}
		</div>
	{/if}

	{#if data.live.length}
		<div class="stats-card" id="mc-live"><div class="stats-label">Registered live tests</div>
			<table class="calib-table"><thead><tr><th>Protocol</th><th>Counting from</th><th>Live matches so far</th><th>Read or planned at</th><th>Reached</th></tr></thead>
				<tbody>{#each data.live as t (t.protocol)}<tr><td>{t.protocol}</td><td>{t.start}</td><td>{t.matches.toLocaleString('en-GB')}</td><td>{t.target.toLocaleString('en-GB')}</td><td>{t.share}%</td></tr>{/each}</tbody></table>
			<p class="stats-note">Finished matches played since each test began that have a prediction stored before kickoff. P13 and P14 are each read once, at their targets, which is the quicker route to a verdict; P15 is the running record above, which has no target.</p>
		</div>
	{/if}

	{#if data.forward}
		<div class="stats-card" id="mc-forward"><div class="stats-label">Since deployment</div>
			<table class="calib-table"><thead><tr><th></th><th>Expected</th><th>Backtest</th><th>Seen since</th><th>Seen less expected</th><th>Matches since</th></tr></thead>
				<tbody><tr><td>Log loss</td><td>{data.forward.expected}</td><td>{data.forward.backtest}</td><td>{data.forward.observed ?? 'Cannot be measured'}</td><td>{data.forward.gap ?? '–'}</td><td>{data.forward.after ? data.forward.after.n.toLocaleString('en-GB') : '–'}</td></tr></tbody></table>
			<p class="stats-note"><b>{data.forward.verdict}.</b> {data.forward.why}</p>
			{#if data.forward.after && data.forward.before}
				<table class="calib-table"><thead><tr><th>Live record</th><th>Matches</th><th>Log loss</th><th>Brier</th><th>Model less market</th><th>Matches with prices</th></tr></thead>
					<tbody>{#each [['Before', data.forward.before], [`Since ${data.forward.from}`, data.forward.after]] as const as [name, w] (name)}
						<tr><td>{name}</td><td>{w.n.toLocaleString('en-GB')}</td><td>{w.log_loss?.toFixed(5) ?? '–'}</td><td>{w.brier?.toFixed(5) ?? '–'}</td><td>{w.vs_market ? w.vs_market.model_minus_market.toFixed(5) : '–'}</td><td>{w.vs_market ? w.vs_market.n.toLocaleString('en-GB') : '–'}</td></tr>
					{/each}</tbody></table>
			{/if}
			<p class="stats-note">"Seen since" is the change in the model's distance from the bookmakers' prices between the live record just before deployment and the record since, each on its own matches. The raw scores are shown but not compared: two periods have different fixtures. {#if data.forward.deployed_with.length}Deployed on the same day as {data.forward.deployed_with.join(', ')}, so their effects cannot be told apart. {/if}Other changes, new data and the run of fixtures can all move these figures; none of it is credited to this change alone.</p>
		</div>
	{/if}

	<div class="stats-card" id="mc-events"><div class="stats-label">What happened, in order</div>
		<table class="calib-table mc-events"><thead><tr><th>#</th><th>Date</th><th>Event</th><th>Recorded</th></tr></thead>
			<tbody>{#each data.events as e (e.n)}<tr><td>{e.n}</td><td>{e.month ? e.date.slice(0, 7) : e.date}</td><td>{e.text}</td><td>{#if e.recorded_at}<LocalTime iso={e.recorded_at} show="short" />{:else}Not yet{/if}</td></tr>{/each}</tbody></table>
		<p class="stats-note">The registration and each event are kept as first recorded{#if c.recorded_at} (the registration on <LocalTime iso={c.recorded_at} show="short" />){/if}; the database refuses any edit or removal. A mistake is put right by a correction, which is a new event.</p>
	</div>
	<p class="stats-note"><a href="/admin/changes">All changes</a></p>
</section>
