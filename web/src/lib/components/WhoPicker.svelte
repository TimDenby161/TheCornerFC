<script lang="ts">
	import Crest from './Crest.svelte';
	import { countryDisplay } from '#lib/clubTable.ts';
	import { FLAG_CODES } from '#lib/names.ts';
	import { whoKey, whoMatches, type WhoClub, type WhoOptions } from '#lib/playerFilters.ts';

	// Club and nationality: pick one or more of each. Two boxes, each opening a list under it:
	// clubs by league (each league opens its clubs) or every nationality, and whatever fits the text
	// once something is typed. `pick` is told the new picks. What the boxes list is fetched when
	// one is first opened.
	type Picked = { clubs: { id: number; name: string }[]; nats: { name: string; flag: string | null }[] };
	let { clubs, nats, pick }: Picked & { pick: (clubs: number[], nats: string[]) => void } = $props();

	let options = $state<WhoOptions | null>(null);
	let asked = false;
	async function load() {
		if (asked) return;
		asked = true;
		try { const r = await fetch('/players/options'); if (r.ok) options = await r.json(); else asked = false; } catch { asked = false; }
	}

	type Kind = 'club' | 'nat';
	let open = $state<Kind | null>(null);
	let text = $state({ club: '', nat: '' });
	let openLeague = $state<number | null>(null);
	let active = $state<string | null>(null); // the highlighted row's key ("c42", "nSpain", "l39")
	const menus: Partial<Record<Kind, HTMLElement>> = {};

	const hasClub = (id: number) => clubs.some((c) => c.id === id);
	const hasNat = (name: string) => nats.some((n) => n.name === name);
	const byId = $derived(new Map((options?.clubs || []).map((c) => [c.id, c])));
	const leagueNames = $derived(new Map((options?.leagues || []).map((l) => [l.id, l.name])));
	const flag = (name: string) => FLAG_CODES[name] ?? FLAG_CODES[countryDisplay(name)];

	// The rows of the open list, in order, for the keyboard: [key, what activating it does]
	type Row = { key: string; kind: 'league' | 'club' | 'nat'; league?: WhoOptions['leagues'][number]; club?: WhoClub; sub?: string; nat?: string };
	const rows = $derived.by((): Row[] => {
		if (!options || !open) return [];
		const q = whoKey(text[open].trim());
		if (open === 'nat') return (q ? whoMatches(options.nats, q) : options.nats).map((n) => ({ key: `n${n.name}`, kind: 'nat', nat: n.name }));
		if (q) return whoMatches(options.clubs, q).map((c) => ({ key: `c${c.id}`, kind: 'club', club: c, sub: leagueNames.get(c.league) }));
		return options.leagues.flatMap((l): Row[] => [
			{ key: `l${l.id}`, kind: 'league', league: l },
			...(openLeague === l.id ? l.clubs.map((id): Row => ({ key: `c${id}`, kind: 'club', club: byId.get(id)! })) : [])
		]);
	});

	function activate(row: Row) {
		if (row.kind === 'league') { openLeague = openLeague === row.league!.id ? null : row.league!.id; return; }
		const clubIds = clubs.map((c) => c.id), natNames = nats.map((n) => n.name);
		if (row.kind === 'club') pick(hasClub(row.club!.id) ? clubIds.filter((x) => x !== row.club!.id) : [...clubIds, row.club!.id], natNames);
		else pick(clubIds, hasNat(row.nat!) ? natNames.filter((x) => x !== row.nat) : [...natNames, row.nat!]);
		// back to the whole list, from the top
		if (open && text[open]) { text[open] = ''; active = null; if (menus[open]) menus[open]!.scrollTop = 0; }
	}
	function move(step: number) {
		if (!rows.length) return;
		const i = rows.findIndex((r) => r.key === active);
		const next = rows[i === -1 ? (step > 0 ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, i + step))];
		active = next.key;
		queueMicrotask(() => menus[open!]?.querySelector('.who-opt.active')?.scrollIntoView({ block: 'nearest' }));
	}
	function keydown(e: KeyboardEvent, kind: Kind) {
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); open = kind; move(e.key === 'ArrowDown' ? 1 : -1); }
		else if (e.key === 'Enter') {
			e.preventDefault();
			// the highlighted row, or the best match when typing
			const row = rows.find((r) => r.key === active) || (text[kind].trim() ? rows[0] : null);
			if (row) activate(row);
		} else if (e.key === 'Escape' && open) { e.preventDefault(); open = null; }
	}
	const focused = (kind: Kind) => { open = kind; active = null; load(); };
	const typed = (kind: Kind) => { active = null; if (menus[kind]) menus[kind]!.scrollTop = 0; };
</script>

{#snippet tick(on: boolean)}<span class="tick" aria-hidden="true">{on ? '✓' : ''}</span>{/snippet}
{#snippet list(kind: Kind)}
	<!-- keep the focus in the box, so the list stays open for another pick -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="who-menu" id="{kind}-menu" role="listbox" tabindex="-1" aria-label={kind === 'club' ? 'Clubs' : 'Nationalities'} hidden={open !== kind} bind:this={menus[kind]} onmousedown={(e) => e.preventDefault()}>
		{#if open === kind}
			{#if !options}
				<div class="who-empty">Loading…</div>
			{:else}
				{#each rows as row (row.key)}
					{#if row.kind === 'league'}
						{@const l = row.league!}
						<button type="button" class="who-opt who-league" class:active={active === row.key} tabindex="-1" aria-expanded={openLeague === l.id} onclick={() => activate(row)}>
							<span class="caret" aria-hidden="true">▾</span>{#if l.country && flag(countryDisplay(l.country))}<img class="flag" src="https://flagcdn.com/w40/{flag(countryDisplay(l.country))}.png" alt="" loading="lazy" />{/if}<span class="nm">{l.name}</span><span class="sub">{l.clubs.length}</span></button>
					{:else if row.kind === 'club'}
						{@const c = row.club!}
						<button type="button" class="who-opt" class:active={active === row.key} class:in-league={!row.sub && !text.club} role="option" tabindex="-1" aria-selected={hasClub(c.id)} onclick={() => activate(row)}>
							{@render tick(hasClub(c.id))}<Crest id={c.id} name={c.name} /><span class="nm">{c.name}</span>{#if row.sub}<span class="sub">{row.sub}</span>{/if}</button>
					{:else}
						<button type="button" class="who-opt" class:active={active === row.key} role="option" tabindex="-1" aria-selected={hasNat(row.nat!)} onclick={() => activate(row)}>
							{@render tick(hasNat(row.nat!))}{#if flag(row.nat!)}<img class="flag" src="https://flagcdn.com/w40/{flag(row.nat!)}.png" alt="" loading="lazy" />{/if}<span class="nm">{row.nat}</span></button>
					{/if}
				{:else}
					<div class="who-empty">No {kind === 'club' ? 'club' : 'nationality'} matches</div>
				{/each}
			{/if}
		{/if}
	</div>
{/snippet}

<div id="who-filter">
	<div class="pos-head"><span>Club &amp; nationality</span>
		<button type="button" class="pos-clear" hidden={!clubs.length && !nats.length} onclick={() => pick([], [])}>Clear</button></div>
	<div class="who-field">
		<input type="search" id="club-input" class="table-search who-input" role="combobox" aria-expanded={open === 'club'} aria-controls="club-menu" aria-autocomplete="list"
			placeholder="Add a club" aria-label="Filter by club" autocomplete="off" bind:value={text.club}
			onfocus={() => focused('club')} oninput={() => typed('club')} onblur={() => (open = null)} onkeydown={(e) => keydown(e, 'club')} />
		{@render list('club')}
	</div>
	<div class="who-field">
		<input type="search" id="nat-input" class="table-search who-input" role="combobox" aria-expanded={open === 'nat'} aria-controls="nat-menu" aria-autocomplete="list"
			placeholder="Add a nationality" aria-label="Filter by nationality" autocomplete="off" bind:value={text.nat}
			onfocus={() => focused('nat')} oninput={() => typed('nat')} onblur={() => (open = null)} onkeydown={(e) => keydown(e, 'nat')} />
		{@render list('nat')}
	</div>
	<div class="who-chips" id="who-chips">
		{#each clubs as c (c.id)}
			<button type="button" class="who-chip" title="Remove" onclick={() => pick(clubs.filter((x) => x.id !== c.id).map((x) => x.id), nats.map((n) => n.name))}>
				<Crest id={c.id} name={c.name} />{c.name}<span class="x" aria-hidden="true">×</span></button>
		{/each}
		{#each nats as n (n.name)}
			<button type="button" class="who-chip" title="Remove" onclick={() => pick(clubs.map((c) => c.id), nats.filter((x) => x.name !== n.name).map((x) => x.name))}>
				{#if n.flag}<img class="flag" src="https://flagcdn.com/w40/{n.flag}.png" alt="" loading="lazy" />{:else}<span class="kind">Nat</span>{/if}{n.name}<span class="x" aria-hidden="true">×</span></button>
		{/each}
	</div>
</div>
