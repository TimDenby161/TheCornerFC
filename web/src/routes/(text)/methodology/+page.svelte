<script lang="ts">
	import raw from '../../../../../docs/methodology.html?raw';
	import { textPage, textParts } from '#lib/textPage.ts';

	let { data } = $props();
	const page = textPage(raw), parts = textParts(page.html);
	const d = $derived(data.live);

	const STALE_HOURS = 36; // the nightly run plus a margin: older than this, say so
	// times in the visitor's time zone as the server has it (the cookie the page sets; UK time until then)
	const when = (iso: string) => new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: data.tz });
	const day = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: data.tz });
	const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
	const num = (x: number) => x.toLocaleString('en-GB');
	const period = (p?: { from: string; to: string }) => (p ? `Kick-offs from ${day(p.from)} to ${day(p.to)}.` : '');
	// how much weight a sample can bear, in words
	const sampleNote = (n: number, what: string) => (n < 500 ? `Very early: ${num(n)} ${what} is far too few to judge the model. These figures will move a lot as more come in.`
		: n < 2000 ? `Still a small sample (${num(n)} ${what}). Small differences are likely to be luck.` : '');
	const versions = (vs: { name: string; n: number }[] | undefined, what: string) => {
		if (!vs?.length) return '';
		const list = vs.map((v) => `${v.name} (${num(v.n)})`).join(', ');
		return vs.length === 1 ? `All ${what} from model version ${list}.` : `Pooled across model versions: ${list}.`;
	};
	const fresh = $derived(d ? ([['Site data exported', d.generated_at], ['Predictions last written', d.freshness?.predictions], ['Injury lists last fetched', d.freshness?.injuries], ['Odds last fetched', d.freshness?.odds]]
		.filter(([, iso]) => iso) as [string, string][]) : []);
	const hours = $derived(d ? (data.now - Date.parse(d.generated_at)) / 36e5 : 0);
</script>

<svelte:head><title>{page.title}</title><meta name="description" content={page.description} /></svelte:head>

{#each parts as part (part.live)}
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- the site's own file, read at build time -->
	{@html part.html}
	{#if part.live}
		<div id={part.live} class="live">
			{#if !d}
				<p class="warn">Couldn't load the live figures. Try reloading the page.</p>
			{:else if part.live === 'fresh-live'}
				<ul class="fresh">{#each fresh as [label, iso] (label)}<li><strong>{label}: </strong>{when(iso)}</li>{/each}</ul>
				{#if hours > STALE_HOURS}<p class="warn">This data is {Math.floor(hours)} hours old, so an update has been missed. Treat predictions and injury news with extra care.</p>{/if}
				<p class="muted">Times are in your time zone.</p>
			{:else if part.live === 'matches-live'}
				{@const m = d.matches}
				{#if !m}
					<p class="muted">No live predictions have been scored yet. Figures appear here once matches predicted before kick-off have finished.</p>
				{:else}
					<p>{num(m.n)} finished matches, each predicted before kick-off. {period(m.period)}</p>
					{#if sampleNote(m.n, 'matches')}<p class="warn">{sampleNote(m.n, 'matches')}</p>{/if}
					<div class="stats">
						<div class="stat"><span class="stat-v">{pct(m.accuracy)}</span><span class="stat-l">Most likely result was right</span></div>
						<div class="stat"><span class="stat-v">{m.log_loss.toFixed(3)}</span><span class="stat-l">Log loss (lower is better)</span></div>
						<div class="stat"><span class="stat-v">{m.brier.toFixed(3)}</span><span class="stat-l">Brier score (lower is better)</span></div>
						{#if m.exact_score?.n}<div class="stat"><span class="stat-v">{pct(m.exact_score.accuracy)}</span><span class="stat-l">Exact score right</span></div>{/if}
					</div>
					<p class="muted">Giving every result a one-in-three chance would score 1.099 and 0.667.</p>
					<p><strong>Calibration</strong>: when the model gave something a certain chance, how often did it happen?</p>
					<table class="calib"><thead><tr><th>Model said</th><th>Average</th><th>It happened</th><th>Predictions</th></tr></thead>
						<tbody>
							{#each m.calibration as [bin, n, mean, seen] (bin)}
								{@const [lo, hi] = bin.split('-').map((x) => Math.round(Number(x) * 100))}
								<tr><td>{lo}–{hi}%</td><td>{Math.round(mean * 100)}%</td><td>{Math.round(seen * 100)}%</td><td>{num(n)}</td></tr>
							{/each}
						</tbody></table>
					<p class="muted">Rows with few predictions say little on their own.</p>
					{#if versions(m.versions, 'predictions are')}<p class="muted">{versions(m.versions, 'predictions are')}</p>{/if}
					{#if m.excluded_no_regulation_score}<p class="muted">{num(m.excluded_no_regulation_score)} matches without a 90-minute score on record are left out.</p>{/if}
				{/if}
			{:else if part.live === 'lineups-live'}
				{@const l = d.lineups}
				{#if !l}
					<p class="muted">No live predicted line-ups have been scored yet. They need a prediction saved before the team sheet came out, and the official XI afterwards.</p>
				{:else}
					<p>{num(l.n)} team line-ups predicted before the official team sheet was published. {period(l.period)}</p>
					{#if sampleNote(l.n, 'line-ups')}<p class="warn">{sampleNote(l.n, 'line-ups')}</p>{/if}
					<div class="stats">
						<div class="stat"><span class="stat-v">{l.correct_starters_mean.toFixed(1)} of 11</span><span class="stat-l">Starters named correctly, on average</span></div>
						{#if l.role_accuracy?.n}<div class="stat"><span class="stat-v">{pct(l.role_accuracy.accuracy)}</span><span class="stat-l">Correct starters in the right position</span></div>{/if}
					</div>
					{#if versions(l.versions, 'line-ups are')}<p class="muted">{versions(l.versions, 'line-ups are')}</p>{/if}
					{#if l.excluded_no_official_xi}<p class="muted">{num(l.excluded_no_official_xi)} line-ups are left out because no complete official XI was recorded.</p>{/if}
				{/if}
			{:else if part.live === 'version-live'}
				{@const model = d.freshness?.model}
				{#if model}<p>The match model in use is <strong>{model.name}</strong>{model.code ? ` (code ${model.code})` : ''}{model.registered ? `, registered ${day(model.registered)}.` : '.'}</p>
				{:else}<p class="muted">The current model version isn't available in this data export.</p>{/if}
			{/if}
		</div>
	{/if}
{/each}
