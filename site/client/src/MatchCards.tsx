import { useEffect, useState, useSyncExternalStore } from 'react';
import { createRoot } from 'react-dom/client';
import type { Spot } from '../../../web/src/lib/lineups.ts';
import type { DetailSection } from '../../../web/src/lib/matchDetail.ts';
import { DetailSections } from './DetailSections.tsx';
import { XiPitch } from './XiPitch.tsx';

// What opens from a match card (MatchCard.svelte): its line-ups, its model detail and how the
// prediction did, each in the place the server left for them ([data-card-panels]), and both clubs'
// expected squads beside their names once the card comes into view. The card itself is the
// server's; this adds what it asks /match/<id>/... for.

type Side = { label: string; kit: string[] | null; ranks: boolean; spots: Spot[] | null; note: string; score: { hits: number; of: number; cls: string } | null };
type Lineups = { locked?: boolean; sides?: Side[]; marked?: boolean; note?: string };
type Detail = { locked?: boolean; sections?: DetailSection[]; notes?: string[] };
type Squad = { attack: number; defence: number; strength: number; recent: number | null; trend: string };
type Rating = { score: number; label: string; factors: { label: string; weight: string; score: number | null }[] };

const get = async <T,>(id: number, part: string): Promise<T | null> => {
	try { const r = await fetch(`/match/${id}/${part}`); return r.ok ? await r.json() : null; } catch { return null; }
};
const Subscriber = () => <a className="link-btn" href="/account?view=subscribe">What subscribers get</a>;

// Which card has a panel open (its line-ups or its model detail). One card at a time in a list:
// opening one closes the last.
type Open = { id: number | null; lineups: boolean; why: boolean };
let open: Open = { id: null, lineups: false, why: false };
const listeners = new Set<() => void>();
function toggle(id: number, part: 'lineups' | 'why') {
	open = open.id !== id ? { id, lineups: false, why: false } : { ...open };
	open[part] = !open[part];
	for (const l of listeners) l();
}
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };
const useOpen = () => useSyncExternalStore(subscribe, () => open);

function LineupsPanel({ id, finished }: { id: number; finished: boolean }) {
	// a line-up can change before kick-off, so it is asked for afresh each time it is opened
	const [d, setD] = useState<Lineups | null | 'loading'>('loading');
	useEffect(() => { let live = true; get<Lineups>(id, 'lineups').then((x) => live && setD(x)); return () => { live = false; }; }, [id]);
	return (
		<div className="fixture-lineup-panel">
			{d === 'loading' ? <div className="empty-state">Loading {finished ? 'actual line-ups' : 'predicted line-ups'}…</div>
				: !d ? <div className="empty-state">Couldn't load the line-ups. Try again in a moment.</div>
				: d.locked ? <div className="empty-state">Predicted line-ups are for subscribers. <Subscriber /></div>
				: <>
					<div className="fixture-lineups">
						{(d.sides || []).map((s) => (
							<div key={s.label}>
								<div className={`modal-section${s.score ? ' xi-head' : ''}`}><span>{s.label}</span>{s.score && <span className={`xi-score xi-score-${s.score.cls}`} title="Starters the model predicted">{s.score.hits}/{s.score.of} predicted</span>}</div>
								{s.spots ? <div className="club-section pp-section"><XiPitch spots={s.spots} kit={s.kit} ranks={s.ranks} /></div> : <div className="page-note">{s.note}</div>}
							</div>
						))}
					</div>
					{d.marked && (
						<div className="xi-legend"><span><i className="xi-key xi-hit"></i>Predicted to start</span><span><i className="xi-key xi-miss"></i>Not predicted</span>
							<span><i className="xi-key-pick">Name <b>70</b></i>The model's pick instead, with his rank going into the match</span></div>
					)}
					{d.note && <div className="page-note">{d.note}</div>}
				</>}
		</div>
	);
}

// the model's detail is asked for once, the first time it is opened
const details = new Map<number, Promise<Detail | null>>();
function DetailPanel({ id }: { id: number }) {
	const [d, setD] = useState<Detail | null | 'loading'>('loading');
	useEffect(() => {
		let live = true;
		if (!details.has(id)) details.set(id, get<Detail>(id, 'detail'));
		details.get(id)!.then((x) => live && setD(x));
		return () => { live = false; };
	}, [id]);
	return (
		<div className="why-detail">
			{d === 'loading' ? <div className="why-note">Loading…</div>
				: !d ? <div className="why-note">Couldn't load the model detail. Try again in a moment.</div>
				: d.locked ? <div className="why-note">The model's detail is for subscribers. <Subscriber /></div>
				: <DetailSections sections={d.sections || []} notes={d.notes || []} />}
		</div>
	);
}

function CardPanels({ id, finished, rating, card }: { id: number; finished: boolean; rating: Rating | null; card: HTMLElement }) {
	const now = useOpen();
	const lineups = now.id === id && now.lineups, why = now.id === id && now.why;
	const [rated, setRated] = useState(false);
	// the server's buttons say whether their panel is open
	useEffect(() => {
		card.querySelector('.lineup-toggle')?.setAttribute('aria-expanded', String(lineups));
		card.querySelector('.why-toggle')?.setAttribute('aria-expanded', String(why));
	}, [card, lineups, why]);
	useEffect(() => {
		const badge = card.querySelector('.rating-badge');
		if (!badge) return;
		badge.setAttribute('aria-expanded', String(rated));
		const flip = () => setRated((r) => !r);
		badge.addEventListener('click', flip);
		return () => badge.removeEventListener('click', flip);
	}, [card, rated]);
	return (
		<>
			{lineups && <LineupsPanel id={id} finished={finished} />}
			{why && <DetailPanel id={id} />}
			{rating && rated && (
				<div className="rating-detail">
					<div className="factor"><span className="factor-name">Overall</span><span className="factor-score">{rating.score}/5 {rating.label}</span></div>
					{rating.factors.map((f) => (
						<div className="factor" key={f.label}><span className="factor-name">{f.label} <span className="factor-weight">{f.weight}</span></span><span className="factor-score">{f.score}/5</span></div>
					))}
				</div>
			)}
		</>
	);
}

// Both clubs' expected squads, beside their names (MatchHead.svelte): worked out from expected
// minutes, not a model input
function squadBadges(card: HTMLElement, squads: { home: Squad; away: Squad }) {
	const badge = (icon: string, value: number, label: string, cls = '') => {
		const b = document.createElement('span');
		b.className = `squad-badge ${cls}`.trim();
		b.title = `${label}: ${value}`;
		const ico = document.createElement('span');
		ico.className = 'ico';
		ico.textContent = icon;
		b.append(ico, String(value));
		return b;
	};
	const note = 'estimated on this page from expected minutes; not a model input';
	const [home, away] = card.querySelectorAll<HTMLElement>('.match-team');
	for (const [team, q, isHome] of [[home, squads.home, true], [away, squads.away, false]] as const) {
		if (!team) continue;
		const names = document.createElement('span');
		names.className = 'team-squad-badges';
		names.append(badge('🛡️', q.defence, `Defence (${note})`), badge('⚔️', q.attack, `Attack (${note})`));
		team.querySelector('.mt-name')?.append(names);
		const overall = document.createElement('span');
		overall.append(badge('⚽', q.strength, `Overall squad rating (${note})${q.recent == null ? '' : `; recent starting XIs ${q.recent}`}`, q.trend));
		const ranks = team.querySelector('.score-badges');
		if (isHome) ranks?.append(overall); else ranks?.prepend(overall);
	}
}

export function matchCards() {
	for (const card of document.querySelectorAll<HTMLElement>('.match-card[data-fixture]')) {
		const id = Number(card.dataset.fixture);
		const slot = card.querySelector<HTMLElement>(':scope > [data-card-panels]');
		if (slot) {
			const data = slot.querySelector(':scope > script[type="application/json"]');
			const rating: Rating | null = data ? JSON.parse(data.textContent || 'null') : null;
			slot.hidden = false;
			createRoot(slot).render(<CardPanels id={id} finished={card.dataset.finished === '1'} rating={rating} card={card} />);
			card.querySelector('.lineup-toggle')?.addEventListener('click', () => toggle(id, 'lineups'));
			card.querySelector('.why-toggle')?.addEventListener('click', () => toggle(id, 'why'));
			// a card opens its line-ups wherever on it the click lands (not on a link or a button)
			if (card.dataset.lineups === '1')
				card.addEventListener('click', (e) => {
					if ((e.target as HTMLElement).closest('a, button, .fixture-lineup-panel, .why-detail, .rating-detail')) return;
					toggle(id, 'lineups');
				});
		}
		// the expected squads: once, when the card first comes into view
		if (card.dataset.squads === '1' && 'IntersectionObserver' in window) {
			const seen = new IntersectionObserver(async (entries) => {
				if (!entries.some((e) => e.isIntersecting)) return;
				seen.disconnect();
				const squads = await get<{ home: Squad; away: Squad } | null>(id, 'squads');
				if (squads) squadBadges(card, squads);
			}, { rootMargin: '200px' });
			seen.observe(card);
		}
	}
}
