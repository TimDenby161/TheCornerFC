// Beat the Model (/beat-the-model, T-095): predict the score of every Premier League match of a
// round before kick-off; the model plays too. A pick is final once saved, and the model's score is
// shown at once (owner's decisions 2026-11-23). Everything is asked of the server as the visitor
// (Site/BeatTheModel.cs), which asks the database with their own token.
import { useCallback, useEffect, useState } from 'react';
import { goals, matchState, nameOk, roundScore, type BtmMatch, type BtmRound, type BtmRow, type BtmTable } from '../../../web/src/lib/beatTheModel.ts';
import { pageHref } from '../../../web/src/lib/menu.ts';
import { Crest } from './Crest.tsx';
import { LocalTime } from './LocalTime.tsx';

const UNREACHABLE = "Couldn't reach the database just now.";
async function ask<T>(path: string, body?: unknown): Promise<T | { ok: false; error: string }> {
	try {
		const r = await fetch(path, body === undefined ? undefined
			: { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
		return (await r.json()) as T;
	} catch { return { ok: false, error: UNREACHABLE }; }
}

export function BeatTheModelPage({ email }: { email: string | null }) {
	const [round, setRound] = useState<BtmRound | null>(null);
	const [asked, setAsked] = useState<number | null>(null);
	const load = useCallback(async (r: number | null) => {
		setRound(null);
		setRound(await ask<BtmRound>(`/btm/round${r ? `?r=${r}` : ''}`));
	}, []);
	useEffect(() => { if (email) void load(asked); }, [email, asked, load]);

	if (!email)
		return <div id="btm-body"><div className="stats-card"><div className="stats-label">This round</div>
			<div className="stats-note">Predict the score of every Premier League match before kick-off: 3 points for the exact score, 1 for the right result. Our model plays too.
				Pick a match and you see the model's score straight away. Free with an account.</div>
			<div className="mt-lock"><a role="button" className="mt-btn owner-signin" href="/account?view=signin">Sign in free to play</a></div>
		</div></div>;
	if (!round) return <div id="btm-body"><div className="stats-card"><div className="stats-label">This round</div><div className="stats-note">Loading…</div></div></div>;
	if (!round.ok) return <div id="btm-body"><div className="stats-card"><div className="stats-label">This round</div>
		<div className="stats-note mt-warn" role="alert">{round.error || UNREACHABLE}</div></div></div>;

	const n = round.round ?? null;
	const put = (m: BtmMatch) => setRound((x) => x && { ...x, matches: (x.matches || []).map((y) => (y.id === m.id ? m : y)) });
	return <div id="btm-body">
		<Name name={round.name ?? null} onSaved={(name) => setRound((x) => x && { ...x, name })} />
		<Round round={round} n={n} step={(by) => n && setAsked(Math.max(1, Math.min(38, n + by)))} put={put} />
		<Table n={n} key={`${round.season}-${n}`} />
	</div>;
}

function Name({ name, onSaved }: { name: string | null; onSaved: (name: string) => void }) {
	const [editing, setEditing] = useState(!name);
	const [text, setText] = useState(name || '');
	const [msg, setMsg] = useState('');
	const save = async () => {
		if (!nameOk(text)) { setMsg('3 to 20 letters or numbers (spaces, dots, dashes and underscores allowed).'); return; }
		const r = await ask<{ ok: boolean; error?: string; name?: string }>('/btm/name', { name: text.trim() });
		if (!r.ok) { setMsg(r.error || UNREACHABLE); return; }
		setMsg(''); setEditing(false); onSaved((r as { name: string }).name);
	};
	if (!editing) return <div className="stats-note" id="btm-name">Playing as <b>{name}</b>{' '}
		<button type="button" className="filter-chip" onClick={() => setEditing(true)}>Change</button></div>;
	return <div className="stats-card" id="btm-name">
		<div className="stats-label">Your name in the table</div>
		<div className="stats-note">Shown to other players instead of your email. You can pick matches without one, but you won't be in the table.</div>
		<form className="btm-name" onSubmit={(e) => { e.preventDefault(); void save(); }}>
			<input className="table-search" id="btm-name-input" maxLength={20} value={text} aria-label="Your name in the table" onChange={(e) => setText(e.currentTarget.value)} />
			<button type="submit" className="mt-btn btm-save">Save name</button>
		</form>
		{msg && <div className="stats-note mt-warn" role="alert">{msg}</div>}
	</div>;
}

function Round({ round, n, step, put }: { round: BtmRound; n: number | null; step: (by: number) => void; put: (m: BtmMatch) => void }) {
	const ms = round.matches || [];
	const score = roundScore(ms);
	const team = (id: number) => round.teams?.[String(id)] || `Team ${id}`;
	return <div className="stats-card" id="btm-round">
		<div className="fpl-filters">
			<span className="stats-label">{n ? `Round ${n}` : 'No round to play yet'}</span>
			{n && <span className="fpl-pager">
				<button type="button" className="filter-chip" aria-label="Previous round" disabled={n <= 1} onClick={() => step(-1)}>◀</button>
				<button type="button" className="filter-chip" aria-label="Next round" disabled={n >= 38} onClick={() => step(1)}>▶</button></span>}
		</div>
		{score.marked > 0 && <div className="btm-total"><span>You <b>{score.you}</b></span><span>The Model <b>{score.model}</b></span>
			<span className="stats-note">from {score.marked} finished {score.marked === 1 ? 'match' : 'matches'}</span></div>}
		<div className="stats-note">A pick is final once saved, and you'll see the model's score straight away. Picks close at kick-off.</div>
		<div className="btm-list">
			{ms.length ? ms.map((m) => <MatchRow key={m.id} m={m} home={team(m.home)} away={team(m.away)} put={put} />)
				: <div className="stats-note">No Premier League matches listed for this round yet.</div>}
		</div>
	</div>;
}

function MatchRow({ m, home, away, put }: { m: BtmMatch; home: string; away: string; put: (m: BtmMatch) => void }) {
	const state = matchState(m, Date.now());
	const [h, setH] = useState(''), [a, setA] = useState('');
	const [msg, setMsg] = useState(''), [busy, setBusy] = useState(false);
	const save = async () => {
		const hg = goals(h), ag = goals(a);
		if (hg === null || ag === null) { setMsg('Enter both scores, 0 to 20.'); return; }
		setBusy(true);
		const r = await ask<{ ok: boolean; error?: string; model?: string | null }>('/btm/pick', { fixture: m.id, home: hg, away: ag });
		setBusy(false);
		if (!r.ok) { setMsg(r.error || UNREACHABLE); return; }
		setMsg('');
		put({ ...m, pick: [hg, ag], model: (r as { model?: string | null }).model ?? null });
	};
	const side = (id: number, name: string, cls: string) =>
		<div className={`btm-side ${cls}`}><Crest id={id} name={name} href={pageHref('club', id)} /><span title={name}>{name}</span></div>;
	return <div className="btm-match" data-fixture={m.id}>
		{side(m.home, home, 'home')}
		<div className="btm-mid">
			{state === 'open'
				? <form className="btm-boxes" onSubmit={(e) => { e.preventDefault(); void save(); }}>
					<input inputMode="numeric" maxLength={2} value={h} aria-label={`${home} goals`} onChange={(e) => setH(e.currentTarget.value)} />
					<span>–</span>
					<input inputMode="numeric" maxLength={2} value={a} aria-label={`${away} goals`} onChange={(e) => setA(e.currentTarget.value)} />
					<button type="submit" className="mt-btn btm-save" disabled={busy}>Lock in</button>
				</form>
				: state === 'done' || state === 'live'
					? <span className="btm-score">{m.hg ?? 0}–{m.ag ?? 0}</span>
					: <span className="btm-score">v</span>}
			<div className="btm-when">{state === 'done' ? 'Full time' : state === 'live' || state === 'missed' ? 'Kicked off' : state === 'off' ? 'Postponed'
				: <><LocalTime iso={m.kickoff} show="day" /> · <LocalTime iso={m.kickoff} show="time" /></>}</div>
			{(m.pick || m.model) && <div className="btm-line">
				{m.pick ? <>You <b>{m.pick[0]}–{m.pick[1]}</b>{m.points != null && <> <span className={`btm-pts p${m.points}`}>{m.points}</span></>}</> : 'No pick'}
				{m.model && <> · Model <b>{m.model.replace('-', '–')}</b>{m.model_points != null && <> <span className={`btm-pts p${m.model_points}`}>{m.model_points}</span></>}</>}
			</div>}
			{msg && <div className="stats-note mt-warn" role="alert">{msg}</div>}
		</div>
		{side(m.away, away, 'away')}
	</div>;
}

function Table({ n }: { n: number | null }) {
	const [which, setWhich] = useState<'season' | 'round'>('season');
	const [t, setT] = useState<BtmTable | null>(null);
	useEffect(() => {
		let gone = false;
		setT(null);
		void ask<BtmTable>(`/btm/table${which === 'round' && n ? `?r=${n}` : ''}`).then((x) => { if (!gone) setT(x); });
		return () => { gone = true; };
	}, [which, n]);
	const row = (r: BtmRow) => <tr key={`${r[0]}-${r[1]}`} className={r[6] ? 'me' : undefined}><td>{r[0]}</td><td className="fpl-player">{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td>{r[5]}</td></tr>;
	const shown = t?.top || [];
	return <div className="stats-card" id="btm-table">
		<div className="fpl-filters"><span className="stats-label">Table</span>
			<button type="button" className="filter-chip" aria-pressed={which === 'season'} onClick={() => setWhich('season')}>Season</button>
			{n && <button type="button" className="filter-chip" aria-pressed={which === 'round'} onClick={() => setWhich('round')}>Round {n}</button>}
		</div>
		{!t ? <div className="stats-note">Loading…</div>
			: !t.ok ? <div className="stats-note mt-warn" role="alert">{t.error || UNREACHABLE}</div>
			: <div className="fpl-scroll"><table className="calib-table btm-table">
				<thead><tr><th>#</th><th>Player</th><th>Pts</th><th title="Exact scores">Exact</th><th title="Right results, exact scores included">Results</th><th>Played</th></tr></thead>
				<tbody>
					{t.model && <tr className="model"><td></td><td className="fpl-player">The Model</td><td>{t.model[0]}</td><td>{t.model[1]}</td><td>{t.model[2]}</td><td>{t.model[3]}</td></tr>}
					{shown.length ? shown.map(row) : <tr><td colSpan={6}>No finished matches yet: the table fills as they are played.</td></tr>}
					{t.me && !shown.some((r) => r[6]) && row(t.me)}
				</tbody></table></div>}
		{t?.ok && !!t.players && <div className="stats-note">{t.players} {t.players === 1 ? 'player' : 'players'} with a name. Ties are split by exact scores.</div>}
	</div>;
}
