// EFL Fantasy (web/src/routes/(app)/efl-fantasy): expected Fantasy EFL points for Championship,
// League One and League Two players and clubs. Nothing comes from the Fantasy EFL site: positions
// are guessed from match data (efl_positions.json corrects them).
import { Fragment, useEffect, useMemo, useState } from 'react';
import { shortName } from '../../../web/src/lib/club.ts';
import { codeOf, EFL_CLUB_PARTS, EFL_LEAGUE_SHORT, EFL_PARTS, EFL_SHOWN, eflClubList, eflClubRows, eflList, eflNext, eflSpan, eflSuggested, FPL_POS,
	oppCode, partLines, predRows, signed, statusTag, teamOf, versus, type ClubCell, type EflView, type FantasyPlayer, type Gameweek, type PredDoc } from '../../../web/src/lib/fantasy.ts';
import { pageHref } from '../../../web/src/lib/menu.ts';
import { Crest } from './Crest.tsx';
import { day, FantasyWho, OwnerGate, Scroll, useFrozenColumns } from './FantasyParts.tsx';
import { askKnown, useOwner, type Owner } from './owner.ts';

const range = (g: Gameweek) => `${day(g.start + 'T12:00:00')} – ${day(g.end + 'T12:00:00')}`;
const pct = (cells: ClubCell[], k: 'p_win' | 'p_clean_sheet') => cells.map((c) => `${Math.round(c[k] * 100)}%`).join(' · ');
const posTitle = (p: FantasyPlayer) => `${FPL_POS[p.position]}${p.corrected ? '' : ': guessed from match data'}`;

export function EflPage({ email }: { email: string | null }) {
	const owner = useOwner(email);
	const d = owner.efl;
	return <div id="efl-body">
		{owner.status !== 'ok'
			? <div className="stats-card"><OwnerGate owner={owner} label="Predictions" signedIn={!!email} why="Fantasy EFL's terms don't allow the game to be used commercially, so this is kept off the public site" /></div>
			: !d || !d.players.length || !d.gameweeks.length ? <div className="stats-card"><div className="stats-note">No upcoming EFL gameweeks yet.</div></div>
			: <Efl owner={owner} d={d} />}
	</div>;
}

function Efl({ owner, d }: { owner: Owner; d: PredDoc }) {
	const players = useMemo(() => predRows(d), [d]);
	const clubRows = useMemo(() => eflClubRows(d), [d]);
	const gws = d.gameweeks;
	const next = useMemo(() => eflNext(gws, Date.now()), [gws]);
	// gw: the gameweek on show, once the pager has moved it off the next one to start
	const [v, setV] = useState<Omit<EflView, 'gw'>>({ pos: 'all', league: 'all', q: '', sort: 'xp', mode: 'gw' });
	const [gwPicked, setGwPicked] = useState<number | null>(null);
	const [all, setAll] = useState(false), [clubsAll, setClubsAll] = useState(false), [open, setOpen] = useState<number | null>(null);
	const change = (c: Partial<EflView>) => { setV((x) => ({ ...x, ...c })); setAll(false); };
	const gw = Math.max(0, Math.min(gwPicked ?? next, gws.length - 1));
	const view = useMemo<EflView>(() => ({ ...v, gw }), [v, gw]);
	const one = v.mode === 'gw';
	const span = useMemo(() => (gws.length ? eflSpan(d, view, next) : []), [d, view, next, gws.length]);
	// the suggested team is for the gameweek shown (the first one in the views over several)
	const g0 = one ? gws[gw] : gws[next];
	const best = useMemo(() => (g0 ? eflSuggested(players, clubRows, view, g0.id) : null), [players, clubRows, view, g0]);
	const rows = useMemo(() => eflList(d, players, view, span), [d, players, view, span]);
	const list = all ? rows : rows.slice(0, EFL_SHOWN);
	const clubs = useMemo(() => eflClubList(d, clubRows, view, span), [d, clubRows, view, span]);
	const clubList = clubsAll ? clubs : clubs.slice(0, 12);
	const cols = one ? 6 : 3 + span.length;
	const ids = [...list.map((r) => r.p.player), ...(best?.xi.map((r) => r.p.player) ?? [])];
	useEffect(() => { void askKnown(ids); }, [ids.join()]); // eslint-disable-line react-hooks/exhaustive-deps
	const frozenPlayers = useFrozenColumns(), frozenClubs = useFrozenColumns();

	const clubParts = (cells: ClubCell[]) => (d.club_part_fields || []).map((k, j) => `${EFL_CLUB_PARTS[k]} ${cells.reduce((a, c) => a + c.parts[j], 0).toFixed(2)}`).join(', ');
	const gwCell = (cs: { xp: number; opponent: number; home: boolean }[], key: number) => cs.length
		? <td key={key} className={`fpl-gw${cs.length > 1 ? ' double' : ''}`}>{cs.reduce((a, c) => a + c.xp, 0).toFixed(1)}<span>{cs.map((c) => oppCode(d, c)).join(' ')}</span></td>
		: <td key={key} className="fpl-gw dim-text">–</td>;
	const name = (p: FantasyPlayer) => owner.known.get(p.player) ? <a className="player-link" href={pageHref('player', p.player)}>{shortName(p.name)}</a> : shortName(p.name);
	const sorts: [EflView['sort'], string, string][] = one ? [['xp', 'Pts', ''], ['minutes', 'Mins', ''], ['goals', 'G', 'Expected goals'], ['assists', 'A', 'Expected assists']] : [['xp', 'Total', '']];

	return <>
		<div className="fpl-filters">
			{[['gw', 'Gameweek'], ['3', 'Next 3'], ['6', 'Next 6']].map(([k, label]) =>
				<button key={k} type="button" className="filter-chip" aria-pressed={v.mode === k} onClick={() => change({ mode: k, ...(k !== 'gw' ? { sort: 'xp' as const } : {}) })}>{label}</button>)}
			{one
				? <span className="fpl-pager"><button type="button" className="filter-chip" aria-label="Previous gameweek" disabled={gw === 0} onClick={() => setGwPicked(gw - 1)}>◀</button>
					<span className="fpl-span">GW{gws[gw].id} · {range(gws[gw])}</span>
					<button type="button" className="filter-chip" aria-label="Next gameweek" disabled={gw === gws.length - 1} onClick={() => setGwPicked(gw + 1)}>▶</button></span>
				: <span className="fpl-span">GW{span[0]}–{span[span.length - 1]}</span>}
		</div>
		<div className="fpl-filters">
			{[['all', 'All leagues'], ...Object.entries(d.leagues || {})].map(([k, label]) =>
				<button key={k} type="button" className="filter-chip" aria-pressed={v.league === k} onClick={() => { change({ league: k }); setClubsAll(false); }}>{label}</button>)}
		</div>

		{best && g0 && <div className="stats-card">
			<div className="stats-label">Suggested team · GW{g0.id} ({range(g0)}) · {(best.total + best.clubs.reduce((a, r) => a + r.xp, 0)).toFixed(1)} expected points</div>
			<div className="mt-pitch">
				{['G', 'D', 'M', 'F'].map((pos) => <div key={pos} className="mt-row">
					{best.xi.filter((r) => r.p.position === pos).map((r) => {
						const tag = statusTag(r.p), cap = best.xi[0].p.player, vice = best.xi[1].p.player;
						return <div key={r.p.player} className="mt-player"><span className="mt-nm">{name(r.p)}{r.p.player === cap ? <>{' '}<b className="mt-c" title="Captain">C</b></> : r.p.player === vice ? <>{' '}<b className="mt-c v" title="Vice-captain">V</b></> : null}</span>
							<small>{codeOf(d, r.p.team)} · {r.xp.toFixed(1)}</small>{tag && <>{' '}<span className="bet-tag warn" title={tag.title}>{tag.text}</span></>}</div>;
					})}
				</div>)}
			</div>
			<div className="stats-label mt-sub">Clubs</div>
			<div className="mt-row mt-bench">
				{best.clubs.map((r) => <div key={r.c.team} className="mt-player"><span className="mt-nm">{teamOf(d, r.c.team)}</span>
					<small>{r.c.cells.filter((c) => c.gw === g0.id).map((c) => `v ${codeOf(d, c.opponent)} ${c.home ? 'H' : 'A'}`).join(' · ')} · {r.xp.toFixed(1)}</small></div>)}
			</div>
			<div className="stats-note">{best.formation}, at most two players from a club, captain (C) on the most expected points.
				{' '}{v.league === 'all' ? '' : `Only ${d.leagues?.[v.league]}. `}It doesn't know how many of your five picks of each club you've used.</div>
		</div>}

		<div className="stats-card">
			<div className="stats-label">Predicted points</div>
			<div className="fpl-filters">
				{[['all', 'All'], ['G', 'GK'], ['D', 'DEF'], ['M', 'MID'], ['F', 'FWD']].map(([k, label]) =>
					<button key={k} type="button" className="filter-chip" aria-pressed={v.pos === k} onClick={() => change({ pos: k })}>{label}</button>)}
				<input type="search" className="table-search fpl-search" id="efl-q" placeholder="Search players or clubs" aria-label="Search players or clubs"
					value={v.q} onChange={(e) => change({ q: e.currentTarget.value })} />
			</div>
			<Scroll>
				<table key={String(one)} className={`calib-table fpl-table${one ? '' : ' multi'}`} ref={frozenPlayers}>
					<thead><tr><th>#</th><th>Player</th>
						{sorts.map(([k, label, title]) =>
							<th key={k} title={title || undefined}><button type="button" className={`fpl-sort${v.sort === k ? ' on' : ''}`} aria-pressed={v.sort === k} aria-label={title || undefined} onClick={() => setV((x) => ({ ...x, sort: k }))}>{label}</button></th>)}
						{!one && span.map((id) => { const g = gws.find((x) => x.id === id); return <th key={id} title={g ? range(g) : undefined}>GW{id}</th>; })}
					</tr></thead>
					<tbody>
						{list.length ? list.map((r, i) => <Fragment key={r.p.player}>
							<tr><td>{i + 1}</td>
								<FantasyWho owner={owner} id={r.p.player} name={r.p.name} team={r.p.team} teamName={teamOf(d, r.p.team)} tag={statusTag(r.p)} line={one ? versus(d, r.cells) : teamOf(d, r.p.team)}
									meta={<span className="fpl-meta"><span title={posTitle(r.p)}>{r.p.position}{r.p.corrected ? '' : '*'}</span> · {EFL_LEAGUE_SHORT[r.p.league ?? 0] || ''}</span>} />
								<td><button type="button" className="fpl-pts" aria-expanded={open === r.p.player} title="Where the points come from" onClick={() => setOpen(open === r.p.player ? null : r.p.player)}><b>{r.xp.toFixed(1)}</b></button></td>
								{one
									? <><td>{r.minutes}</td><td>{r.goals.toFixed(2)}</td><td>{r.assists.toFixed(2)}</td></>
									: span.map((id) => gwCell(r.cells.filter((c) => c.gw === id), id))}
							</tr>
							{open === r.p.player && <tr className="fpl-break"><td className="fpl-parts-cell" colSpan={cols}><div className="fpl-parts">
								{partLines(d, r, EFL_PARTS, false).map((x) => <div key={x.label} className="fpl-part"><span>{x.label}</span><span>{x.figure}</span><b className={x.value < 0 ? 'neg' : undefined}>{signed(x.value)}</b></div>)}
							</div></td></tr>}
						</Fragment>) : <tr><td colSpan={cols}>No players match.</td></tr>}
					</tbody>
				</table>
			</Scroll>
			{rows.length > EFL_SHOWN && <button type="button" className="show-all" id="efl-more" onClick={() => setAll(!all)}>{all ? 'Show fewer' : `Show all ${rows.length}`}</button>}
		</div>

		<div className="stats-card">
			<div className="stats-label">Club picks</div>
			<Scroll>
				<table key={String(one)} className={`calib-table fpl-table${one ? '' : ' multi'}`} ref={frozenClubs}>
					<thead><tr><th>#</th><th>Club</th>
						{one ? <><th>Pts</th><th title="Chance of winning">Win</th><th title="Chance of a clean sheet">CS</th></>
							: <><th>Total</th>{span.map((id) => <th key={id}>GW{id}</th>)}</>}
					</tr></thead>
					<tbody>
						{clubList.length ? clubList.map((r, i) => <tr key={r.c.team}><td>{i + 1}</td>
							<td className="fpl-player"><div className="fpl-who"><Crest id={r.c.team} name={teamOf(d, r.c.team)} size="efl-club-logo" />
								<div className="fpl-name"><div className="fpl-line"><span className="fpl-nm">{teamOf(d, r.c.team)}</span><span className="fpl-meta">{EFL_LEAGUE_SHORT[r.c.league ?? 0] || ''}</span></div>
									{one && <div className="fpl-match">{versus(d, r.cells)}</div>}</div></div></td>
							{one
								? <><td title={clubParts(r.cells)}><b>{r.xp.toFixed(1)}</b></td><td>{pct(r.cells, 'p_win')}</td><td>{pct(r.cells, 'p_clean_sheet')}</td></>
								: <><td><b>{r.xp.toFixed(1)}</b></td>{span.map((id) => gwCell(r.cells.filter((c) => c.gw === id), id))}</>}
						</tr>) : <tr><td colSpan={5}>No clubs match.</td></tr>}
					</tbody>
				</table>
			</Scroll>
			{clubs.length > 12 && <button type="button" className="show-all" id="efl-clubs-more" onClick={() => setClubsAll(!clubsAll)}>{clubsAll ? 'Show fewer' : `Show all ${clubs.length}`}</button>}
		</div>

		<div className="stats-card"><div className="stats-note">
			Points use Fantasy EFL's scoring. Everyone: 1 for playing, 2 for 60 minutes, 3 an assist, 5 a hat-trick, −3 a missed penalty, −1 a yellow and −3 a red.
			Goals: 10 goalkeeper, 7 defender, 6 midfielder, 5 forward. Goalkeepers and defenders: 5 a clean sheet (60+ minutes), −1 per 2 conceded; goalkeepers 2 per 3 saves and 5 a penalty save.
			Defenders: 1 per 2 tackles, per 2 blocks and per 4 clearances. Midfielders: 2 an interception. Midfielders and forwards: 1 per 2 key passes and 1 a shot on target.
			Clubs: 5 a win (2 more away), 3 a draw, 2 a clean sheet, 2 for 2+ goals and 2 more for 4+.
			<br /><br />Minutes, goals, assists, penalties, clean sheets, saves and cards come from the same model as the FPL tab, run on each division's own matches and our match predictions.
			Tackles, blocks, interceptions, key passes and shots on target are each player's own rates over the last year, pulled toward his role's when he's played little.
			Our match data has no clearances, so defenders get a typical rate for their role (centre-backs 5 a match, full-backs 2.2): a rough guess. Own goals aren't included.
			<br /><br />Positions marked * are guessed from match data and may not match Fantasy EFL's; corrected ones have no mark.
			Gameweeks run Thursday to Wednesday, numbered from the season's first week, so check the numbers against the game. Predictions further ahead assume today's form and fitness.
			This is {d.model}, not yet tested against real Fantasy EFL scores: a guide, not a pick list. Click a player's points to see where they come from.</div></div>
	</>;
}
