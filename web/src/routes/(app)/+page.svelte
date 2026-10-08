<script lang="ts">
	import { openAccount } from '#lib/account.svelte.ts';
	import Crest from '#lib/components/Crest.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';
	import Move from '#lib/components/Move.svelte';
	import XiPitch from '#lib/components/XiPitch.svelte';
	import { rankTier } from '#lib/club.ts';
	import { pageHref } from '#lib/menu.ts';
	import '#lib/placed.css';

	let { data } = $props();
	// the example line-up arrives after the rest of the page (the server doesn't wait for it)
	type Xi = Awaited<typeof data.xi>;
	let xi = $state<Xi>(null);
	$effect(() => { let live = true; data.xi.then((v) => { if (live) xi = v; }); return () => { live = false; }; });

	// The hero turns through a slide for each part of the site. A slide whose sample of the real
	// thing couldn't be had is left out.
	const slides = $derived([
		{ key: 'clubs', name: 'Clubs', on: true }, { key: 'players', name: 'Players', on: !!data.players }, { key: 'matches', name: 'Matches', on: !!data.calls },
		{ key: 'lineups', name: 'Line-ups', on: !!xi }, { key: 'stats', name: 'Stats', on: !!data.stats },
		{ key: 'leagues', name: 'Leagues', on: data.leagues.length > 0 }, { key: 'nations', name: 'Nations', on: !!data.nations }
	].filter((s) => s.on));
	let upKey = $state('clubs');  // the slide that's up, by name (a slide that arrives late can join to its left)
	const up = $derived(Math.max(0, slides.findIndex((s) => s.key === upKey)));
	$effect(() => { void slides.length; if (box) box.scrollLeft = left(up); });
	let box = $state<HTMLElement>();
	const left = (i: number) => { const el = box!.children[i] as HTMLElement; return el.offsetLeft - (box!.firstElementChild as HTMLElement).offsetLeft; };
	function slideTo(i: number, slid = !matchMedia('(prefers-reduced-motion: reduce)').matches) {
		upKey = slides[i].key;
		if (slid) box!.scrollTo({ left: left(i), behavior: 'smooth' }); else box!.scrollLeft = left(i);
	}
	// the rule over the name of the slide that's up fills as its ten seconds pass (the stylesheet's
	// home-fill is the clock): when it ends, the next slide comes up
	const filled = (e: AnimationEvent) => { if (e.animationName === 'home-fill') slideTo((up + 1) % slides.length); };
	// a swipe (or any scroll of the slides) that comes to rest on another slide makes that one the one that's up
	let rest: ReturnType<typeof setTimeout> | undefined;
	function scrolled() {
		clearTimeout(rest);
		rest = setTimeout(() => {
			const x = box!.scrollLeft;
			let near = 0;
			for (let i = 1; i < slides.length; i++) if (Math.abs(left(i) - x) < Math.abs(left(near) - x)) near = i;
			if (near !== up) upKey = slides[near].key;
		}, 120);
	}
	// the headline's number, counted up to once; set outright where motion is turned down
	let count = $state(0);
	$effect(() => {
		const n = data.clubCount;
		if (matchMedia('(prefers-reduced-motion: reduce)').matches) { count = n; return; }
		const from = performance.now();
		let frame = requestAnimationFrame(function step(now) {
			const t = Math.min(1, (now - from) / 1100);
			count = Math.round(n * (1 - (1 - t) ** 3));
			if (t < 1) frame = requestAnimationFrame(step);
		});
		return () => cancelAnimationFrame(frame);
	});
	let counting = $state(false);
	$effect(() => { counting = true; });
	const join = (e: Event) => { e.preventDefault(); openAccount('signup'); };
</script>

<svelte:head>
	<title>The Corner FC</title>
	<meta name="description" content="Club strength ratings, projected scores and model win/draw/loss chances." />
	<meta property="og:type" content="website" /><meta property="og:site_name" content="The Corner FC" /><meta property="og:title" content="The Corner FC" />
	<meta property="og:description" content="Club strength ratings, projected scores and model win/draw/loss chances." />
</svelte:head>

{#snippet slide(key: string, name: string, first: string, second: string, lede: string, go: string, href: string, head: string, note: string, sample: import('svelte').Snippet)}
	<div class="home-slide" role="group" aria-roledescription="slide" aria-label={name} inert={upKey !== key}>
		<div class="home-copy"><h2 class="home-title"><span>{first}</span> <em>{second}</em></h2><p class="home-lede">{lede}</p>
			<div class="home-actions"><a class="mt-btn home-go" {href}>{go}</a></div></div>
		<div class="home-board"><p class="home-board-head"><span class="home-dot" aria-hidden="true"></span>{head}<span class="home-board-key">{note}</span></p>
			<div class="home-sample">{@render sample()}</div></div>
	</div>
{/snippet}

<section class="panel" data-tab="home" data-active="true">
	<div class="home-hero" role="region" aria-roledescription="carousel" aria-label="What's on the site">
		<!-- the corner of a pitch: the touchline and goal line, the corner arc and the flag (the site's mark) -->
		<svg class="home-pitch" viewBox="0 0 420 300" aria-hidden="true" focusable="false">
			<g fill="none" stroke="currentColor" stroke-width="2"><path d="M-4000 110H372V4000" /><path d="M328 110a44 44 0 0 0 44 44" /></g>
			<path d="M372 110V22" fill="none" stroke="#c9c8c2" stroke-width="3" stroke-linecap="round" />
			<g class="home-flag"><path d="M371 24H326V56z" fill="#ffffff" /><path d="M371 24V56H326z" fill="#0b110e" /></g>
		</svg>
		<div class="home-slides" bind:this={box} onscroll={scrolled}>
			<div class="home-slide" role="group" aria-roledescription="slide" aria-label="Clubs" inert={upKey !== 'clubs'}>
				<div class="home-copy">
					<h2 class="home-title"><span>{(counting ? count : data.clubCount).toLocaleString('en-GB')}</span> clubs. <em>One&nbsp;scale.</em></h2>
					<p class="home-lede">One strength rating for every club, from the Premier League to the lower divisions, with ranks for players and national teams and the model's chances for the matches they play.</p>
					<div class="home-actions">
						<a class="mt-btn home-go" href="/clubs">See the ratings</a>
						{#if !data.user}<a class="home-ghost" href="/account?view=signup" onclick={join}>Create a free account</a>{/if}
					</div>
				</div>
				<div class="home-board">
					<p class="home-board-head"><span class="home-dot" aria-hidden="true"></span>Strongest clubs now<span class="home-board-key">Rating · last 6</span></p>
					<ol class="home-top">
						{#each data.clubs as x (x.team)}
							<li><Crest id={x.team} name={x.name} href="/club/{x.team}" /><span class="lg-main"><a class="team-link" href="/club/{x.team}">{x.name}</a><span class="lg-sub">{x.comp}</span></span><b>{x.current.toLocaleString('en-GB')}</b><span class="home-form"><Move value={x.form} /></span></li>
						{/each}
					</ol>
					<a class="home-board-more" href="/clubs">All {data.clubCount.toLocaleString('en-GB')} clubs</a>
				</div>
			</div>
			{#if data.players}
				{#snippet sample()}
					<ol class="home-top">
						{#each data.players! as p (p.id)}
							<li>{#if p.team && p.teamName}<Crest id={p.team} name={p.teamName} />{:else}<span class="club-logo"></span>{/if}<span class="lg-main"><span class="home-who"><a class="team-link" href="/player/{p.id}">{p.name}</a>{#if p.nat}{#if p.flag}<a class="pl-flag" href={pageHref('nation', p.nat)} title={p.nat} aria-label="{p.nat} national team"><img class="flag" src="https://flagcdn.com/w40/{p.flag}.png" alt="" loading="lazy" /></a>{/if}{/if}</span><span class="lg-sub">{p.teamName ?? 'Club not known'}{p.league ? ` · ${p.league}` : ''}</span></span><span class="home-pos">{p.pos}</span><span class="rel-chip rel-{rankTier(p.rank)}">{Math.round(p.rank)}</span></li>
						{/each}
					</ol>
				{/snippet}
				{@render slide('players', 'Players', 'Players.', '0 to 100.', data.intro.players, 'See the players', '/players', 'Highest-ranked players', 'Position · rank', sample)}
			{/if}
			{#if data.calls}
				{#snippet sample()}
					{#each data.calls!.calls as m (m.id)}
						<div class="home-call"><span class="home-call-teams">{m.home} <i>v</i> {m.away}</span>
							<span class="home-call-when">{m.comp} · <LocalTime iso={m.kickoff} show="day" />, <LocalTime iso={m.kickoff} show="time" /></span>
							<span class="home-call-bar" role="img" aria-label="{m.home} {m.h}%, draw {m.d}%, {m.away} {m.a}%"><span class="prob-home sw-{m.h}"></span><span class="prob-draw sw-{m.d}"></span><span class="prob-away sw-{m.a}"></span></span>
							<span class="home-call-key" aria-hidden="true"><span><b>{m.h}%</b>{m.home}</span><span><b>{m.d}%</b>Draw</span><span><b>{m.a}%</b>{m.away}</span></span></div>
					{/each}
				{/snippet}
				{@render slide('matches', 'Matches', 'Matches.', 'Forecast.', data.intro.matches, 'See the matches', `/matches?d=${data.calls.day}`, "The model's chances", '', sample)}
			{/if}
			{#if xi}
				{#snippet sample()}
					<p class="home-xi-head" class:home-xi-bare={xi!.bare}><span>{xi!.what}</span><span class="xi-score xi-score-{xi!.cls}" title="Starters the model predicted">{xi!.hits}/{xi!.of} predicted</span></p>
					<div class="club-section pp-section"><XiPitch spots={xi!.spots} /></div>
					<div class="xi-legend"><span><i class="xi-key xi-hit"></i>Predicted to start</span><span><i class="xi-key xi-miss"></i>Not predicted</span></div>
					{#if xi!.note}<p class="home-nums-note">{xi!.note}</p>{/if}
				{/snippet}
				{@render slide('lineups', 'Line-ups', 'The eleven.', 'Called.', "Each club's predicted starting eleven for its next match, marked against the real team sheet afterwards.", 'See the line-up record', '/lineups', 'Predicted against the team sheet', '', sample)}
			{/if}
			{#if data.stats}
				{#snippet sample()}
					<dl class="home-nums">{#each data.stats!.nums as [n, unit, what] (what)}<div><dt>{n}{#if unit}<small>{unit}</small>{/if}</dt><dd>{what}</dd></div>{/each}</dl>
					{#if data.stats!.note}<p class="home-nums-note">{data.stats!.note}</p>{/if}
				{/snippet}
				{@render slide('stats', 'Stats', data.stats.matches, 'Matches.', "The last year's match predictions, each one marked against the real result, so you can see how often the model is right.", 'See the record', '/stats', 'The last 12 months', '', sample)}
			{/if}
			{#if data.leagues.length}
				{#snippet sample()}
					<ol class="home-top">{#each data.leagues as c (c.lid)}<li><Crest id={c.lid} name={c.name} league /><span class="lg-main"><a class="team-link" href="/league/{c.lid}">{c.name}</a><span class="lg-sub">{c.sub}</span></span><span class="rel-chip rel-{c.tier}">{c.lt}</span></li>{/each}</ol>
				{/snippet}
				{@render slide('leagues', 'Leagues', 'Leagues.', 'Compared.', data.intro.leagues, 'See the leagues', '/leagues', 'Strongest leagues now', 'Average rating', sample)}
			{/if}
			{#if data.nations}
				{#snippet sample()}
					<ol class="home-top">{#each data.nations! as n (n.name)}<li><span class="home-flag-cell">{#if n.flag}<img class="flag" src="https://flagcdn.com/w40/{n.flag}.png" alt="" loading="lazy" />{/if}</span><span class="lg-main"><span class="team-link">{n.name}</span><span class="lg-sub">{n.confed}</span></span><span class="rel-chip rel-{n.tier}">{n.current.toLocaleString('en-GB')}</span><span class="home-form"><Move value={n.change} /></span></li>{/each}</ol>
				{/snippet}
				{@render slide('nations', 'Nations', 'Nations.', 'Since 1872.', data.intro.nations, 'See the nations', '/nations', 'Strongest national teams', 'Rating', sample)}
			{/if}
		</div>
		<!-- which slide is up, and the way to another: the rule over the one that's up fills as its ten seconds pass -->
		{#if slides.length > 1}
			<div class="home-turn">
				{#key up}
					<div class="home-turn-list" onanimationend={filled}>
						{#each slides as s, i (s.key)}<button type="button" aria-current={i === up ? 'true' : undefined} onclick={() => slideTo(i)}><span>{s.name}</span></button>{/each}
					</div>
				{/key}
			</div>
		{/if}
	</div>
	<!-- the four things a first visit asks, each a label, a one-line answer and the detail under it -->
	<div class="home-brief">
		<section class="home-brief-item">
			<h3 class="home-brief-q">What it is</h3>
			<p class="home-brief-a">Football ratings on one scale</p>
			<p>Every club gets one strength number, updated after each match it plays. Around it: players ranked 0 to 100, national team ratings, and win, draw and loss chances for the matches coming up.</p>
		</section>
		<section class="home-brief-item">
			<h3 class="home-brief-q">Who it's for</h3>
			<p class="home-brief-a">Fans who want more than the league table</p>
			<ul>
				<li>You follow a club and want to know where it really stands.</li>
				<li>You argue about which league or player is better, and want a number.</li>
				<li>You like a prediction that shows its reasons.</li>
			</ul>
			<p class="home-brief-note">The numbers are estimates, <a href="/terms#advice" data-sveltekit-reload>not betting or fantasy advice</a>.</p>
		</section>
		<section class="home-brief-item">
			<h3 class="home-brief-q">Why it matters</h3>
			<p class="home-brief-a">A league table only compares clubs that play each other</p>
			<p>One scale sets a lower-division side against a Champions League club: 100 points is about a goal a game. And every match prediction is marked against the real result, so you can see how often the model is right.</p>
		</section>
		<section class="home-brief-item home-brief-next">
			<h3 class="home-brief-q">What to do next</h3>
			<p class="home-brief-a">Start with your own club</p>
			<ol class="home-steps">
				<li><a href="/clubs">Find your club</a><span>Search for it in the table and open its page.</span></li>
				<li><a href="/matches">See its next match</a><span>The model's chances, before kick-off.</span></li>
				<li><a href="/stats">Check the record</a><span>How the predictions have done against results.</span></li>
			</ol>
		</section>
	</div>
	<div class="home-close">
		<p class="home-close-line">Ratings you can check.</p>
		<p class="home-close-sub">How the models work is written up in full, and the Stats page marks their match predictions against what happened.</p>
		<div class="home-actions">
			<a class="mt-btn home-go" href="/clubs">See the ratings</a>
			<a class="home-ghost" href="/methodology" data-sveltekit-reload>How the models work</a>
		</div>
	</div>
</section>
