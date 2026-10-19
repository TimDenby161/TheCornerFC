import { Fragment, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { countryDisplay } from '../../../web/src/lib/clubTable.ts';
import { FLAG_CODES } from '../../../web/src/lib/names.ts';
import { whoKey, whoMatches, type WhoClub, type WhoOptions } from '../../../web/src/lib/playerFilters.ts';
import { choose } from './choose.ts';
import { Crest } from './Crest.tsx';

// Club and nationality: pick one or more of each (WhoPicker.svelte). Two boxes, each opening a list
// under it: clubs by league (each league opens its clubs) or every nationality, and whatever fits
// the text once something is typed. What the boxes list is fetched when one is first opened. The
// picks are the server's (props); a pick goes to the page, which brings the new ones back.
type Picked = { clubs: { id: number; name: string }[]; nats: { name: string; flag: string | null }[] };
type Kind = 'club' | 'nat';
type Row = { key: string; kind: 'league' | 'club' | 'nat'; league?: WhoOptions['leagues'][number]; club?: WhoClub; sub?: string; nat?: string };

let options: Promise<WhoOptions | null> | null = null;
const loadOptions = () => (options ??= fetch('/players/options').then((r) => (r.ok ? r.json() : null)).catch(() => null)
	.then((o) => { if (!o) options = null; return o; }));

const flag = (name: string) => FLAG_CODES[name] ?? FLAG_CODES[countryDisplay(name)];
const pick = (clubs: number[], nats: string[]) => choose({ club: clubs.join(','), nat: nats.join('|') });

export function WhoPicker({ clubs, nats }: Picked) {
	const [opts, setOpts] = useState<WhoOptions | null>(null);
	const [open, setOpen] = useState<Kind | null>(null);
	const [text, setText] = useState({ club: '', nat: '' });
	const [openLeague, setOpenLeague] = useState<number | null>(null);
	const [active, setActive] = useState<string | null>(null); // the highlighted row's key ("c42", "nSpain", "l39")
	const menus = { club: useRef<HTMLDivElement>(null), nat: useRef<HTMLDivElement>(null) };

	const hasClub = (id: number) => clubs.some((c) => c.id === id);
	const hasNat = (name: string) => nats.some((n) => n.name === name);
	const byId = useMemo(() => new Map((opts?.clubs || []).map((c) => [c.id, c])), [opts]);
	const leagueNames = useMemo(() => new Map((opts?.leagues || []).map((l) => [l.id, l.name])), [opts]);

	// The rows of the open list, in order, for the keyboard
	const rows = useMemo((): Row[] => {
		if (!opts || !open) return [];
		const q = whoKey(text[open].trim());
		if (open === 'nat') return (q ? whoMatches(opts.nats, q) : opts.nats).map((n) => ({ key: `n${n.name}`, kind: 'nat', nat: n.name }));
		if (q) return whoMatches(opts.clubs, q).map((c) => ({ key: `c${c.id}`, kind: 'club', club: c, sub: leagueNames.get(c.league) }));
		return opts.leagues.flatMap((l): Row[] => [
			{ key: `l${l.id}`, kind: 'league', league: l },
			...(openLeague === l.id ? l.clubs.map((id): Row => ({ key: `c${id}`, kind: 'club', club: byId.get(id)! })) : [])
		]);
	}, [opts, open, text, openLeague, byId, leagueNames]);

	function activate(row: Row) {
		if (row.kind === 'league') { setOpenLeague(openLeague === row.league!.id ? null : row.league!.id); return; }
		const clubIds = clubs.map((c) => c.id), natNames = nats.map((n) => n.name);
		if (row.kind === 'club') pick(hasClub(row.club!.id) ? clubIds.filter((x) => x !== row.club!.id) : [...clubIds, row.club!.id], natNames);
		else pick(clubIds, hasNat(row.nat!) ? natNames.filter((x) => x !== row.nat) : [...natNames, row.nat!]);
		// back to the whole list, from the top
		if (open && text[open]) { setText({ ...text, [open]: '' }); setActive(null); if (menus[open].current) menus[open].current.scrollTop = 0; }
	}
	function move(kind: Kind, step: number) {
		if (!rows.length) return;
		const i = rows.findIndex((r) => r.key === active);
		const next = rows[i === -1 ? (step > 0 ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, i + step))];
		setActive(next.key);
		queueMicrotask(() => requestAnimationFrame(() => menus[kind].current?.querySelector('.who-opt.active')?.scrollIntoView({ block: 'nearest' })));
	}
	function keydown(e: KeyboardEvent, kind: Kind) {
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); setOpen(kind); move(kind, e.key === 'ArrowDown' ? 1 : -1); }
		else if (e.key === 'Enter') {
			e.preventDefault();
			// the highlighted row, or the best match when typing
			const row = rows.find((r) => r.key === active) || (text[kind].trim() ? rows[0] : null);
			if (row) activate(row);
		} else if (e.key === 'Escape' && open) { e.preventDefault(); setOpen(null); }
	}
	const focused = (kind: Kind) => { setOpen(kind); setActive(null); loadOptions().then((o) => o && setOpts(o)); };
	const typed = (kind: Kind, value: string) => { setText({ ...text, [kind]: value }); setActive(null); if (menus[kind].current) menus[kind].current.scrollTop = 0; };

	const tick = (on: boolean) => <span className="tick" aria-hidden="true">{on ? '✓' : ''}</span>;
	const list = (kind: Kind) => (
		// keep the focus in the box, so the list stays open for another pick
		<div className="who-menu" id={`${kind}-menu`} role="listbox" tabIndex={-1} aria-label={kind === 'club' ? 'Clubs' : 'Nationalities'} hidden={open !== kind}
			ref={menus[kind]} onMouseDown={(e) => e.preventDefault()}>
			{open === kind && (!opts ? <div className="who-empty">Loading…</div>
				: !rows.length ? <div className="who-empty">No {kind === 'club' ? 'club' : 'nationality'} matches</div>
				: rows.map((row) => {
					const cls = `who-opt${active === row.key ? ' active' : ''}`;
					if (row.kind === 'league') {
						const l = row.league!, f = l.country ? flag(countryDisplay(l.country)) : null;
						return <button type="button" key={row.key} className={`${cls} who-league`} tabIndex={-1} aria-expanded={openLeague === l.id} onClick={() => activate(row)}>
							<span className="caret" aria-hidden="true">▾</span>{f && <img className="flag" src={`https://flagcdn.com/w40/${f}.png`} alt="" loading="lazy" />}<span className="nm">{l.name}</span><span className="sub">{l.clubs.length}</span></button>;
					}
					if (row.kind === 'club') {
						const c = row.club!;
						return <button type="button" key={row.key} className={`${cls}${!row.sub && !text.club ? ' in-league' : ''}`} role="option" tabIndex={-1} aria-selected={hasClub(c.id)} onClick={() => activate(row)}>
							{tick(hasClub(c.id))}<Crest id={c.id} name={c.name} /><span className="nm">{c.name}</span>{row.sub && <span className="sub">{row.sub}</span>}</button>;
					}
					const f = flag(row.nat!);
					return <button type="button" key={row.key} className={cls} role="option" tabIndex={-1} aria-selected={hasNat(row.nat!)} onClick={() => activate(row)}>
						{tick(hasNat(row.nat!))}{f && <img className="flag" src={`https://flagcdn.com/w40/${f}.png`} alt="" loading="lazy" />}<span className="nm">{row.nat}</span></button>;
				}))}
		</div>
	);
	const box = (kind: Kind, placeholder: string, label: string) => (
		<div className="who-field">
			<input type="search" id={`${kind}-input`} className="table-search who-input" role="combobox" aria-expanded={open === kind} aria-controls={`${kind}-menu`} aria-autocomplete="list"
				placeholder={placeholder} aria-label={label} autoComplete="off" value={text[kind]}
				onFocus={() => focused(kind)} onChange={(e) => typed(kind, e.currentTarget.value)} onBlur={() => setOpen(null)} onKeyDown={(e) => keydown(e, kind)} />
			{list(kind)}
		</div>
	);

	return (
		<>
			<div className="pos-head"><span>Club &amp; nationality</span>
				<button type="button" className="pos-clear" hidden={!clubs.length && !nats.length} onClick={() => pick([], [])}>Clear</button></div>
			{box('club', 'Add a club', 'Filter by club')}
			{box('nat', 'Add a nationality', 'Filter by nationality')}
			<div className="who-chips" id="who-chips">
				{clubs.map((c) => (
					<button type="button" key={`c${c.id}`} className="who-chip" title="Remove" onClick={() => pick(clubs.filter((x) => x.id !== c.id).map((x) => x.id), nats.map((n) => n.name))}>
						<Crest id={c.id} name={c.name} />{c.name}<span className="x" aria-hidden="true">×</span></button>
				))}
				{nats.map((n) => (
					<Fragment key={`n${n.name}`}>
						<button type="button" className="who-chip" title="Remove" onClick={() => pick(clubs.map((c) => c.id), nats.filter((x) => x.name !== n.name).map((x) => x.name))}>
							{n.flag ? <img className="flag" src={`https://flagcdn.com/w40/${n.flag}.png`} alt="" loading="lazy" /> : <span className="kind">Nat</span>}{n.name}<span className="x" aria-hidden="true">×</span></button>
					</Fragment>
				))}
			</div>
		</>
	);
}
