<script lang="ts">
	import ChangeLines from '#lib/components/ChangeLines.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';
	import { METRIC_LABELS, shortId, signed, stepPoints } from '#lib/changes.ts';
	import { MATCH_MODEL_LABELS, otherModel } from '#lib/matchModels.ts';

	let { data, form } = $props();
	const refused = $derived((form as { message?: string } | null)?.message ?? '');
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
		{#if data.model}
			<div class="stats-card mc-switch" id="mc-switch"><div class="stats-label">Live match model</div>
				<div class="stats-value mc-value">{MATCH_MODEL_LABELS[data.model.live]}</div>
				{#if data.versus}{@const v = data.versus}
					<div class="mc-compare" id="mc-compare">
						<div class="stats-label">The bookmakers, the base model and A18 compared</div>
						<p class="mc-para"><strong>On past matches</strong> (A18’s test before release, against the released base model): {#if v.pastScores.n}<strong>{v.pastScores.n.toLocaleString('en-GB')} matches</strong>{#if v.pastScores.period}{' '}from {v.pastScores.period[0]} to {v.pastScores.period[1]}{/if}. That period had been looked at before, so the live matches are the real test.{:else if v.past}log loss {v.past.delta}{#if v.past.low && v.past.high}{' '}(range {v.past.low} to {v.past.high}){/if}.{:else}no test recorded.{/if}</p>
						<p class="mc-para"><strong>On live matches</strong>, both predictions stored before kickoff{#if v.start}, from {v.start}{/if}:{#if !v.scores}{' '}not available yet.{:else if !v.scores.n}{' '}no finished matches yet.{:else}{' '}<strong>{v.scores.n.toLocaleString('en-GB')} finished match{v.scores.n === 1 ? '' : 'es'}</strong>, {v.scores.priced ? `${v.scores.priced.toLocaleString('en-GB')} of them with bookmaker prices` : 'none of them with bookmaker prices yet'}.{/if}</p>
						{#if v.scores?.n || v.pastScores.rows.length}
							<div class="mc-scroll"><table class="calib-table mc-rows mc-two" id="mc-two"><thead><tr><th>Measure</th><th>Bookmakers</th><th>Base</th><th>A18</th><th>A18 − Bookmakers</th><th>A18 − Base</th></tr></thead>
								{#if v.pastScores.rows.length}<tbody><tr class="mc-group"><th colspan="6">Past matches{#if v.pastScores.period}, {v.pastScores.period[0]} to {v.pastScores.period[1]}{/if}</th></tr>
									<tr class="mc-count"><td>Matches</td><td>–</td><td>{v.pastScores.n?.toLocaleString('en-GB') ?? '–'}</td><td>{v.pastScores.n?.toLocaleString('en-GB') ?? '–'}</td><td>–</td><td>{v.pastScores.n?.toLocaleString('en-GB') ?? '–'}</td></tr>
									{#each v.pastScores.rows as r (r.label)}<tr><td>{r.label}</td><td>–</td><td>{r.base}</td><td>{r.a18}</td><td>–</td><td><span class="mc-pill {r.mark}">{r.gap}</span></td></tr>{/each}</tbody>{/if}
								{#if v.scores?.n}<tbody><tr class="mc-group"><th colspan="6">Live matches{#if v.start}, from {v.start}{/if}</th></tr>
								<tr class="mc-count"><td>Matches</td><td>{v.scores.priced || '–'}</td><td>{v.scores.n}</td><td>{v.scores.n}</td><td>{v.scores.priced || '–'}</td><td>{v.scores.n}</td></tr>
									{#each v.scores.rows as r (r.label)}<tr><td>{r.label}</td><td>{r.market ?? 'No prices'}</td><td>{r.base}</td><td>{r.a18}</td>
										<td>{#if r.marketGap}<span class="mc-pill {r.marketMark}">{r.marketGap}</span>{#if r.marketNote}<span class="mc-sub">{r.marketNote}</span>{/if}{:else}–{/if}</td>
										<td><span class="mc-pill {r.mark}">{r.gap}</span></td></tr>{/each}</tbody>{/if}</table></div>
							<div class="stats-note">The bookmakers are their closing prices with the margin taken out, averaged; there are no clean stored prices for the past period, so it has none{#if v.scores?.priced && v.scores.priced < v.scores.n}. Only {v.scores.priced} of the {v.scores.n} matches have prices, so the Bookmakers column and A18 − Bookmakers are on those {v.scores.priced}, with A18's own figure on them under the gap{/if}. Minus is better for A18 on log loss and Brier, plus on right results.</div>
						{/if}
						<p class="mc-para"><strong>The verdict</strong> (protocol P18): {#if v.p18}{#if v.p18.verdict === 'better'}A18 is proven better.{:else if v.p18.verdict === 'worse'}A18 is proven worse.{:else}not proven either way yet.{/if}{#if v.p18.delta}{' '}Log loss {v.p18.delta}{#if v.p18.low && v.p18.high}, and the true gap could still be anywhere from {v.p18.low} to {v.p18.high}{/if}.{/if} {v.p18.n.toLocaleString('en-GB')} matches over {v.p18.weeks} week{v.p18.weeks === 1 ? '' : 's'}; nothing is called before {v.p18.matches} matches and {v.p18.minWeeks} weeks{#if v.target}, and a call is expected at about {v.target.toLocaleString('en-GB')}{/if}. Updated <LocalTime iso={v.p18.generated} show="short" />, Mondays and Thursdays.{:else}the Live tracking job has not scored it yet (Mondays and Thursdays).{/if}</p>
						{#if v.upcoming}<p class="mc-para"><strong>Upcoming fixtures:</strong> {v.upcoming}</p>{/if}
						{#if v.apart.length}
							<div class="stats-label">Where they differ most · home · draw · away chances, expected goals</div>
							<div class="mc-scroll"><table class="calib-table mc-rows mc-apart" id="mc-apart"><thead><tr><th>Kick-off</th><th>Match</th><th>Bookmakers</th><th>Base</th><th>A18</th><th>Gap</th></tr></thead>
								<tbody>{#each v.apart as r (r.fixture)}<tr class:mc-differ={r.differ}><td><LocalTime iso={r.kickoff} show="short" /></td><td><a class="team-link" href="/match/{r.fixture}">{r.match}</a><span class="mc-sub">{r.league}{r.differ ? ' · different favourite' : ''}</span></td>
									<td>{r.market ?? 'No prices yet'}</td><td>{r.base}<span class="mc-sub">xG {r.baseXg}</span></td><td>{r.a18}<span class="mc-sub">xG {r.a18Xg}</span></td><td>{r.gap}</td></tr>{/each}</tbody></table></div>
						{/if}
					</div>
				{/if}
				<form method="POST" action="?/switch"><input type="hidden" name="live" value={otherModel(data.model.live)} />
					<button type="submit" class="mt-btn">Make live: {MATCH_MODEL_LABELS[otherModel(data.model.live)]}</button></form>
				{#if refused}<div class="sim-banner mc-alert" role="alert">{refused}</div>{/if}
				<div class="stats-note">The live model is the one the site, the paper bets and the fantasy models use, from the next run of the predictions (several a day). Both models' predictions are stored before every kickoff whichever is live, and compared on the same matches (P18).{#if data.model.switches.length} Last switched <LocalTime iso={data.model.switches[0].at} show="short" /> <LocalTime iso={data.model.switches[0].at} show="time" />.{/if}</div></div>
		{/if}
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
			<div class="stats-card"><div class="stats-label">3 · Running total across deployed versions, log loss</div>
				{#if data.steps.some((s) => s.delta != null)}
					<ChangeLines label="Cumulative change in log loss across deployed changes" zero places={4} series={[{ name: 'Sum of each deployed change’s own backtest', cls: 'live', points: stepPoints(data.steps) }]} />
				{/if}
				<table class="calib-table mc-steps"><thead><tr><th>Deployed</th><th>Change</th><th>Its backtest</th><th>Total</th></tr></thead>
					<tbody>{#each data.steps as s (s.id)}<tr><td>{s.on.slice(0, 7)}</td><td><a class="team-link" href="/admin/changes/{s.id}">{shortId(s.id)} · {s.title}</a></td><td>{s.delta != null ? signed(s.delta) : 'No test recorded'}</td><td>{signed(s.total)}</td></tr>{/each}</tbody></table>
				<div class="stats-note">Match-model changes that are in production, in the order they went live. Each figure comes from that change's own test on its own sample, so the total is a sum of separate tests and not a measurement. Changes made before this record began were never dated and are not here.</div>
			</div>
			<div class="stats-card mc-wide"><div class="stats-label">2 · Each change against the current version, {data.metricLabel.toLowerCase()}</div>
				{#if data.deltas.length}
					<table class="calib-table mc-rows mc-versus" id="mc-versus"><thead><tr><th>No.</th><th>Change</th><th>Past matches</th><th>Past gain</th><th>Current → with the change</th><th>Live matches</th><th>Live gain</th><th>On live matches</th></tr></thead>
						<tbody>{#each data.deltas as d (d.id)}
							<tr class="mark-{d.mark}" class:mc-ready={d.ready}><td class="mc-no">{shortId(d.id)}</td>
								<td><a class="team-link" href="/admin/changes/{d.id}">{d.title}</a>{#if d.readyNote}<span class="mc-sub" class:mc-ready-note={d.ready}>{d.readyNote}</span>{/if}</td>
								<td>{d.n != null ? d.n.toLocaleString('en-GB') : '–'}</td>
								<td>{#if d.gain != null}<span class="mc-gain mark-{d.mark}">{signed(d.gain)}</span>{:else}–{/if}{#if d.expected != null}<span class="mc-sub">Expected {signed(d.expected)}</span>{/if}</td>
								<td>{d.before != null && d.after != null ? `${d.before.toFixed(5)} → ${d.after.toFixed(5)}` : d.gain == null ? '–' : 'Not recorded'}</td>
								<td>{d.liveRecord ? d.liveRecord.n.toLocaleString('en-GB') : '–'}</td>
								<td class="mc-live">{#if d.liveRecord?.gain != null}{signed(d.liveRecord.gain)}{#if d.liveRecord.low != null && d.liveRecord.high != null}<span class="mc-sub">{signed(d.liveRecord.low)} to {signed(d.liveRecord.high)}</span>{/if}{:else}–{/if}</td>
								<td class="mc-live-say" title={d.liveWhy}>{d.liveText}{#if d.liveWhy}<span class="mc-sub">{d.liveWhy}</span>{/if}</td></tr>
						{/each}</tbody></table>
					<div class="stats-note">{#if data.live}Live matches: {data.live.n.toLocaleString('en-GB')} finished since {data.live.start}{#if data.live.to} (to {data.live.to}){/if}, over {data.live.weeks} week{data.live.weeks === 1 ? '' : 's'}, for the {data.live.tracked} change{data.live.tracked === 1 ? '' : 's'} tracked ({data.live.protocol}). Updated <LocalTime iso={data.live.generated} show="short" />. Nothing is called on live matches before {data.live.matches} matches and {data.live.minWeeks} weeks.{:else}The live record has not been stored yet: it is written by the Live tracking job, on Mondays and Thursdays.{/if} The live gain is the candidate against the current model on the same live matches, with the range it could still lie in; it is judged by a method that allows looking at any time, which is why its range is wide and a call takes many matches.</div>
					<div class="stats-note"><b>Green means one thing: implement this.</b> A row is green when there is statistical evidence that the change makes the model better, however small the gain: on live matches, or on a test that was not the matches it was built on, and it has been neither rejected nor deployed. No other change is marked green anywhere on this page. A gain that is large but unproven, or rejected, has no colour and says why under its name. Red is a change a test has proven worse. Releasing a green change is still your decision. Green rows come first, then proven gains, then the unproven, then the proven losses. Gain is how much lower the {data.metricLabel.toLowerCase()} is with the change, so a plus is an improvement. Past figures are each change's own historical test on its own matches, never a production result.</div>
				{:else}<div class="stats-note">No change outside production in this selection has a result on {data.metricLabel.toLowerCase()}.</div>{/if}
			</div>
		</div>

		<details class="stats-card mc-list" id="mc-list"><summary class="stats-label">Every change ({data.rows.length} of {data.all}): deployed, rejected and still to decide</summary>
			{#if data.rows.length}
				<div class="mc-scroll"><table class="calib-table mc-table"><thead><tr><th>Change</th><th>Date</th><th>Part of the model</th><th>Where it stands</th><th>Expected</th><th>Result</th><th>Since deployment</th></tr></thead>
					<tbody>{#each data.rows as r (r.id)}
						<tr><td><a class="team-link" href="/admin/changes/{r.id}">{r.title}</a><span class="mc-sub">{shortId(r.id)} · {r.kind}</span></td>
							<td>{r.date}</td><td>{r.component}</td>
							<td><span class="mc-stage {STAGE[r.stage] ?? (r.stage.startsWith('In production') ? 'deployed' : 'other')}">{r.stage}</span>{#if r.status !== r.stage}<span class="mc-sub">{r.status}</span>{/if}</td>
							<td>{r.expected}</td>
							<td>{#if r.result}<span class="mc-pill mark-{r.result.mark}">{r.result.word} {r.result.text}</span><span class="mc-sub">{r.result.kind}{r.result.metric !== data.metricLabel ? ` · ${r.result.metric}` : ''}{r.result.n ? ` · ${r.result.n.toLocaleString('en-GB')} matches` : ''}</span>{:else}No result recorded{/if}</td>
							<td>{r.forward ?? '–'}</td></tr>
					{/each}</tbody></table></div>
			{:else}<div class="stats-note">No change matches these choices.</div>{/if}
		</details>
	{/if}
</section>
