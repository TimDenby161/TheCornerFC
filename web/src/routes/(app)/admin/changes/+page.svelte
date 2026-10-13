<script lang="ts">
	import ChangeBar from '#lib/components/ChangeBar.svelte';
	import ChangeLines from '#lib/components/ChangeLines.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';
	import { METRIC_LABELS, reach, shortId, signed } from '#lib/changes.ts';

	let { data } = $props();
	const STAGE: Record<string, string> = { 'Deployed to production': 'deployed', 'Tested and rejected': 'rejected', 'Being tested': 'testing', Reverted: 'reverted' };
	const SOURCE = { live: ['Stored before kickoff', 'live'], backfill: ['Reconstructed history', 'recon'] } as const;
</script>

<svelte:head>
	<title>Model Change Tracker · The Corner FC</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<section class="panel mc" data-tab="changes" data-active="true">
	{#if !data.ready}
		<div class="empty-state">The model change record has not been stored yet. It is written by the next export after the Admin migration is applied.</div>
	{:else}
		<p class="mc-env" id="mc-env">{data.environment === 'production' ? 'Production' : data.environment === 'staging' ? 'Staging: test data, not the live record' : 'Environment not named'} · updated <LocalTime iso={data.generated} show="short" /> <LocalTime iso={data.generated} show="time" /></p>
		{#if !data.stored}<div class="sim-banner mc-alert" role="alert">This copy was read from the register's files and could not be recorded in the database, so nothing here is yet protected from later edits.</div>{/if}
		{#if data.differs.length}
			<div class="sim-banner mc-alert" role="alert">A file in the register no longer matches what was first recorded. The record below is the first version; put a mistake right with a correction, not an edit.
				<ul>{#each data.differs as line (line)}<li>{line}</li>{/each}</ul></div>
		{/if}

		<div class="stats-grid mc-tiles" id="mc-tiles">
			{#each data.tiles as t (t.label)}
				<div class="stats-card"><div class="stats-label">{t.label}</div><div class="stats-value mc-value"><span class={t.cls}>{t.value}</span></div><div class="stats-note">{t.note}</div></div>
			{/each}
		</div>

		<form class="mc-filters" id="mc-filters" method="GET" action="/admin/changes" data-sveltekit-reset="false">
			<label>Status <select name="status"><option value="all">All</option>{#each data.statuses as s (s)}<option value={s} selected={data.choices.status === s}>{s}</option>{/each}</select></label>
			<label>Part of the model <select name="component"><option value="all">All</option>{#each data.components as s (s)}<option value={s} selected={data.choices.component === s}>{s}</option>{/each}</select></label>
			<label>Measure <select name="metric"><option value="all">All (charts on log loss)</option>{#each data.metrics as [k, name] (k)}<option value={k} selected={data.choices.metric === k}>{name}</option>{/each}</select></label>
			<label>From <input type="date" name="from" value={data.choices.from} /></label>
			<label>To <input type="date" name="to" value={data.choices.to} /></label>
			<button type="submit" class="mt-btn">Show</button>
			<a class="mc-clear" href="/admin/changes">Clear</a>
		</form>

		<div class="mc-charts" id="mc-charts">
			<div class="stats-card"><div class="stats-label">1 · The match model over time, {data.lineLabel.toLowerCase()}</div>
				{#if data.lines.length}
					<ChangeLines label="{data.lineLabel} by month" series={data.lines.map((l) => ({ name: SOURCE[l.source][0], cls: SOURCE[l.source][1], points: l.points.map((p) => ({ x: p.month, value: p.value, note: `${p.n.toLocaleString('en-GB')} matches` })) }))} />
					<div class="stats-note">By month of kickoff, result market, lower is better. The reconstructed line is today's model replayed over the past, so it does not show what earlier versions said, and it moves with the mix of fixtures as much as with the model. Only the line stored before kickoff is a record.</div>
				{:else}<div class="stats-note">No monthly figures yet.</div>{/if}
			</div>
			<div class="stats-card"><div class="stats-label">4 · Running total across deployed versions, log loss</div>
				{#if data.steps.some((s) => s.delta != null)}
					<ChangeLines label="Cumulative change in log loss across deployed changes" zero places={4} series={[{ name: 'Sum of each deployed change’s own backtest', cls: 'live', points: data.steps.map((s) => ({ x: s.on.slice(0, 7), value: s.total, note: s.title })) }]} />
				{/if}
				<table class="calib-table mc-steps"><thead><tr><th>Deployed</th><th>Change</th><th>Its backtest</th><th>Total</th></tr></thead>
					<tbody>{#each data.steps as s (s.id)}<tr><td>{s.on.slice(0, 7)}</td><td><a class="team-link" href="/admin/changes/{s.id}">{shortId(s.id)} · {s.title}</a></td><td>{s.delta != null ? signed(s.delta) : 'No test recorded'}</td><td>{signed(s.total)}</td></tr>{/each}</tbody></table>
				<div class="stats-note">Match-model changes that are in production, in the order they went live. Each figure comes from that change's own test on its own sample, so the total is a sum of separate tests and not a measurement. Changes made before this record began were never dated and are not here.</div>
			</div>
			<div class="stats-card"><div class="stats-label">2 · Each change against the current version, {data.metricLabel.toLowerCase()}</div>
				{#if data.deltas.length}
					<table class="calib-table mc-rows mc-versus" id="mc-versus"><thead><tr><th>No.</th><th>Change</th><th>Past matches</th><th>Past gain</th><th>Current → with the change</th><th>Live matches</th><th>Live gain</th><th>On live matches</th></tr></thead>
						<tbody>{#each data.deltas as d (d.id)}
							<tr class="mark-{d.mark}" class:mc-ready={d.ready}><td class="mc-no">{shortId(d.id)}</td>
								<td><a class="team-link" href="/admin/changes/{d.id}">{d.title}</a>{#if d.readyNote}<span class="mc-sub" class:mc-ready-note={d.ready}>{d.readyNote}</span>{/if}</td>
								<td>{d.n != null ? d.n.toLocaleString('en-GB') : '–'}</td>
								<td><span class="mc-gain mark-{d.mark}">{signed(d.gain)}</span></td>
								<td>{d.before != null && d.after != null ? `${d.before.toFixed(5)} → ${d.after.toFixed(5)}` : 'Not recorded'}</td>
								<td>{d.liveRecord ? d.liveRecord.n.toLocaleString('en-GB') : '–'}</td>
								<td class="mc-live">{#if d.liveRecord?.gain != null}{signed(d.liveRecord.gain)}{#if d.liveRecord.low != null && d.liveRecord.high != null}<span class="mc-sub">{signed(d.liveRecord.low)} to {signed(d.liveRecord.high)}</span>{/if}{:else}–{/if}</td>
								<td class="mc-live-say" title={d.liveWhy}>{d.liveText}{#if d.liveWhy}<span class="mc-sub">{d.liveWhy}</span>{/if}</td></tr>
						{/each}</tbody></table>
					<div class="stats-note">{#if data.live}Live matches: {data.live.n.toLocaleString('en-GB')} finished since {data.live.start}{#if data.live.to} (to {data.live.to}){/if}, over {data.live.weeks} week{data.live.weeks === 1 ? '' : 's'}, for the {data.live.tracked} changes that can be run. Updated <LocalTime iso={data.live.generated} show="short" />. Nothing is called on live matches before {data.live.matches} matches and {data.live.minWeeks} weeks.{:else}The live record has not been stored yet: it is written by the Live tracking job, on Mondays and Thursdays.{/if} The live gain is the candidate against the current model on the same live matches, with the range it could still lie in; it is judged by a method that allows looking at any time, which is why its range is wide and a call takes many matches.</div>
					<div class="stats-note"><b>Green means one thing: implement this.</b> A row is green only when there is statistically enough evidence that the change is an improvement of at least the 0.002 bar: on live matches, or on a test that was not the matches it was built on, and it has been neither rejected nor deployed. No other change is marked green anywhere on this page. A gain that is proven but too small, large but unproven, or rejected has no colour and says why under its name. Red is a change a test has proven worse. Releasing a green change is still your decision. Green rows come first, then proven gains, then the unproven, then the proven losses. Gain is how much lower the {data.metricLabel.toLowerCase()} is with the change, so a plus is an improvement. Past figures are each change's own historical test on its own matches, never a production result.</div>
				{:else}<div class="stats-note">No change in this selection has a result on {data.metricLabel.toLowerCase()}.</div>{/if}
			</div>
			<div class="stats-card"><div class="stats-label">3 · Expected against actual</div>
				{#if data.expected.length}
					{@const widest = reach(data.expected.flatMap((e) => [e.expected, e.actual]))}
					<table class="calib-table mc-rows"><thead><tr><th>Change</th><th>Expected</th><th>Actual</th><th>Expected (top) and actual</th></tr></thead>
						<tbody>{#each data.expected as e (e.id + e.metric)}
							<tr><td><a class="team-link" href="/admin/changes/{e.id}">{shortId(e.id)} · {e.title}</a><span class="mc-sub">{METRIC_LABELS[e.metric]}</span></td>
								<td>{signed(e.expected)}</td><td>{e.actual != null ? signed(e.actual) : 'Not tested yet'}</td>
								<td><ChangeBar delta={e.expected} second={e.actual} reach={widest} tone="plain" label="{e.title}: expected {signed(e.expected)}, actual {e.actual != null ? signed(e.actual) : 'not tested yet'}" /></td></tr>
						{/each}</tbody></table>
					<div class="stats-note">Only changes that wrote a number down before testing are here; every other change says Not specified. The actual figure is from a test, never from the matches the change was built on.</div>
				{:else}<div class="stats-note">No change in this selection recorded a number before it was tested.</div>{/if}
			</div>
		</div>

		<div class="stats-card" id="mc-list"><div class="stats-label">{data.rows.length} of {data.all} changes</div>
			{#if data.rows.length}
				<div class="mc-scroll"><table class="calib-table mc-table"><thead><tr><th>Change</th><th>Date</th><th>Part of the model</th><th>Where it stands</th><th>Expected</th><th>Result</th><th>Since deployment</th></tr></thead>
					<tbody>{#each data.rows as r (r.id)}
						<tr><td><a class="team-link" href="/admin/changes/{r.id}">{r.title}</a><span class="mc-sub">{shortId(r.id)} · {r.kind}</span></td>
							<td>{r.date}</td><td>{r.component}</td>
							<td><span class="mc-stage {STAGE[r.stage] ?? 'other'}">{r.stage}</span>{#if r.status !== r.stage}<span class="mc-sub">{r.status}</span>{/if}</td>
							<td>{r.expected}</td>
							<td>{#if r.result}<span class="mc-pill mark-{r.result.mark}">{r.result.word} {r.result.text}</span><span class="mc-sub">{r.result.kind}{r.result.metric !== data.metricLabel ? ` · ${r.result.metric}` : ''}{r.result.n ? ` · ${r.result.n.toLocaleString('en-GB')} matches` : ''}</span>{:else}No result recorded{/if}</td>
							<td>{r.forward ?? '–'}</td></tr>
					{/each}</tbody></table></div>
			{:else}<div class="stats-note">No change matches these choices.</div>{/if}
		</div>
	{/if}
</section>
