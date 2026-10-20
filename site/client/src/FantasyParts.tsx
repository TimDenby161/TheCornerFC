// What the three fantasy pages share: the note anyone but the owner sees, a player's cell in their
// tables, and the first column that stays put as a table scrolls sideways
import { useCallback, type ReactNode } from 'react';
import { personInitials, shortName } from '../../../web/src/lib/club.ts';
import { pageHref } from '../../../web/src/lib/menu.ts';
import { Crest } from './Crest.tsx';
import type { Owner } from './owner.ts';

// What an owner-only part shows anyone else: a short why, and a way to sign in (OwnerGate.svelte).
// The sign-in link opens the account box (AccountBox.tsx), or the account page before scripts run.
export function OwnerGate({ owner, label, signedIn, why = "it's built on FPL's own data (prices, positions, availability and gameweeks), which FPL's terms don't allow us to republish" }:
	{ owner: Owner; label: string; signedIn: boolean; why?: string }) {
	return <>
		<div className="stats-label">{label}</div>
		{signedIn && (owner.status === 'idle' || owner.status === 'busy')
			? <div className="stats-note">Loading…</div>
			: <>
				<div className="stats-note">Shown to the site owner only: {why}.</div>
				{!signedIn && <div className="mt-lock"><a role="button" className="mt-btn owner-signin" href="/account?view=signin">Sign in</a></div>}
				{owner.error && signedIn && <div className="stats-note mt-warn" role="alert">{owner.error}</div>}
			</>}
	</>;
}

// A player's cell in a fantasy table (FantasyWho.svelte): initials with his club's chip on the
// corner; surname (full name on hover, a link where he has a page here), then `meta` (position,
// price), any doubt over him, and a line below (his match, or his club).
export function FantasyWho({ owner, id, name, team, teamName, tag, line, meta }:
	{ owner: Owner; id: number; name: string; team: number; teamName: string; tag: { text: string; title: string } | null; line: string; meta: ReactNode }) {
	return <td className="fpl-player"><div className="fpl-who"><span className="fpl-face"><span className="player-photo person-chip" aria-hidden="true"><b>{personInitials(name)}</b></span>
		{' '}<Crest id={team} name={teamName} href={pageHref('club', team)} /></span>
		<div className="fpl-name"><div className="fpl-line"><span className="fpl-nm" title={name}>{owner.known.get(id) ? <a className="player-link" href={pageHref('player', id)}>{shortName(name)}</a> : shortName(name)}</span>{meta}{tag && <>{' '}<span className="bet-tag warn" title={tag.title}>{tag.text}</span></>}</div>
			<div className="fpl-match">{line}</div></div></div></td>;
}

// The first column's width, for the second to stick beside it (frozenColumns in actions.ts)
export function useFrozenColumns() {
	return useCallback((table: HTMLTableElement | null) => {
		if (!table) return;
		const set = () => { const first = table.tHead?.rows[0]?.cells[0]; if (first) table.style.setProperty('--fz2', `${first.getBoundingClientRect().width}px`); };
		set();
		const watch = new ResizeObserver(set);
		watch.observe(table);
		return () => watch.disconnect();
	}, []);
}

// "Sat 10 Oct", in the browser's own zone, as the Svelte pages write a gameweek's day
export const day = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });

// A table that scrolls sideways on a narrow screen
export const Scroll = ({ children }: { children: ReactNode }) =>
	<div className="fpl-scroll" tabIndex={0} role="group" aria-label="Table: scrolls sideways">{children}</div>;
