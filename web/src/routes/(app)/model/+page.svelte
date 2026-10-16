<script lang="ts">
	import LocalTime from '#lib/components/LocalTime.svelte';
	import { shortId, signed } from '#lib/changes.ts';

	let { data } = $props();
	const REPO = 'https://github.com/TimDenby161/TheCornerFC';
</script>

<svelte:head>
	<title>The Model · The Corner FC</title>
	<meta name="description" content="How good The Corner FC's match model is, in the open: its locked pre-kickoff record, how it compares with the bookmakers, and every change made to it with the test behind it." />
</svelte:head>

<section class="panel mc" data-tab="model" data-active="true">
	{#if !data.ready}
		<div class="empty-state" id="model-empty">The model's public record is being prepared. It is written by the nightly run.</div>
	{:else}
		<p class="mc-env" id="model-updated">{#if data.version}Live model: {data.version} · {/if}updated <LocalTime iso={data.generated} show="short" /></p>

		<h2 class="mc-h2">The record</h2>
		<p class="stats-note">Every figure comes from predictions stored before kick-off. The database refuses any change to a stored prediction, so this record can't be tidied up afterwards. Where the model trails the bookmakers, it says so.</p>
		<div class="stats-grid mc-tiles" id="model-tiles">
			{#each data.tiles as t (t.label)}
				<div class="stats-card"><div class="stats-label">{t.label}</div><div class="stats-value mc-value"><span class={t.cls}>{t.value}</span></div><div class="stats-note">{t.note}</div></div>
			{/each}
		</div>
		<p class="stats-note">The model against the bookmakers on every bet market, competition by competition, is on the <a href="/stats">Stats</a> page.</p>

		<h2 class="mc-h2">Every change, and the test behind it</h2>
		<p class="stats-note">{data.registered} changes are on the record. Each was written down, with how it would be judged, before its result was seen. Past figures are each change's own test on earlier matches; live figures are on matches played after it was written down.</p>
		{#each [{ id: 'model-in', title: 'In the model now', rows: data.inModel }, { id: 'model-tried', title: 'Tried, or being tested', rows: data.tried }] as group (group.id)}
			{#if group.rows.length}
				<div class="stats-card"><div class="stats-label">{group.title}</div>
					<div class="mc-scroll"><table class="calib-table mc-rows mc-versus" id={group.id}><thead><tr><th>No.</th><th>Change</th><th>Past matches</th><th>Past gain</th><th>Live matches</th><th>Live gain</th><th>On live matches</th></tr></thead>
						<tbody>{#each group.rows as d (d.id)}
							<tr class="mark-{d.mark}"><td class="mc-no">{shortId(d.id)}</td>
								<td>{d.title}{#if d.readyNote}<span class="mc-sub">{d.readyNote}</span>{/if}</td>
								<td>{d.n != null ? d.n.toLocaleString('en-GB') : '–'}</td>
								<td>{#if d.gain != null}<span class="mc-gain mark-{d.mark}">{signed(d.gain)}</span>{:else}–{/if}</td>
								<td>{d.liveRecord ? d.liveRecord.n.toLocaleString('en-GB') : '–'}</td>
								<td class="mc-live">{#if d.liveRecord?.gain != null}{signed(d.liveRecord.gain)}{#if d.liveRecord.low != null && d.liveRecord.high != null}<span class="mc-sub">{signed(d.liveRecord.low)} to {signed(d.liveRecord.high)}</span>{/if}{:else}–{/if}</td>
								<td class="mc-live-say">{d.liveText}{#if d.liveWhy}<span class="mc-sub">{d.liveWhy}</span>{/if}</td></tr>
						{/each}</tbody></table></div>
				</div>
			{/if}
		{/each}
		<p class="stats-note">Gain is how much lower the log loss is with the change, so a plus is an improvement. Green: statistical evidence the change makes the model better. Red: evidence it makes it worse. No colour: not proven either way yet.
			{#if data.live}Live tests: {data.live.n.toLocaleString('en-GB')} finished matches since {data.live.start}, over {data.live.weeks} week{data.live.weeks === 1 ? '' : 's'}, for {data.live.tracked} change{data.live.tracked === 1 ? '' : 's'} ({data.live.protocol}). Nothing is called before {data.live.matches} matches and {data.live.minWeeks} weeks, and the method allows looking at any time, which is why its ranges are wide.{/if}</p>

		<h2 class="mc-h2">Check it yourself</h2>
		<ul class="stats-note" id="model-check">
			<li>The model's code is public: <a href={`${REPO}/tree/main/thecornerfc/models`} rel="noopener">the models</a>, and <a href={`${REPO}/tree/main/experiments/changes`} rel="noopener">the register of every change</a>.</li>
			<li>Each model version is named by a fingerprint of its code files, so an edit, even a comment, makes a new version: <a href={`${REPO}/blob/main/tests/test_model_fingerprints.py`} rel="noopener">the fingerprints</a>.</li>
			<li>Every test is written before its result is seen: <a href={`${REPO}/blob/main/experiments/prospective/PROTOCOLS.md`} rel="noopener">the registered protocols</a>.</li>
			<li>What the measures mean and how each model works: <a href="/methodology" data-sveltekit-reload>How the models work</a>.</li>
		</ul>
	{/if}
</section>
