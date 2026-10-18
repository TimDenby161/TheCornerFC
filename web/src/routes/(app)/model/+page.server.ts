import { deltaRows, inProduction, scoreTiles, type ChangesDoc, type LiveDoc } from '#lib/changes.ts';
import { matchDetail, type Why } from '#lib/matchDetail.ts';
import type { Match } from '#lib/matches.ts';
import { keptDocOrNull } from '#lib/server/database.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';

// The Model (owner's decision 2026-10-16, the most transparent model): the live model's record
// and every change to it, in public. The nightly export writes it (thecornerfc/publish/
// site_record.py, public_model): the Model Change Tracker's record and the live tests' results,
// without the Admin area's own notes. The model switch and where the two models part on matches
// to come stay in the Admin area.
// example: one finished match worked through step by step (site_matches.worked_example), its row
// as site.matches holds it, by field name
type Example = { match: Match; home_name: string | null; away_name: string | null; competition: string | null; why: Why };
type ModelDoc = Pick<ChangesDoc, 'generated_at' | 'current' | 'series' | 'changes'> & { tracking: LiveDoc | null; example?: Example | null };

function workedExample(ex: Example | null | undefined) {
	if (!ex?.why?.steps) return null;
	const m = ex.match, home = ex.home_name || 'Home', away = ex.away_name || 'Away';
	const { sections, notes } = matchDetail(m, ex.why, home, away);
	return { home, away, competition: ex.competition, kickoff: m.kickoff, hg: m.hg, ag: m.ag, sections, notes };
}

export async function load({ fetch, setHeaders, locals }) {
	const tabHead = { title: 'The Model', ...TAB_INFO.model };
	const doc = await keptDocOrNull<ModelDoc>(fetch, 'model', 300_000);
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=300' });
	if (!doc) return { tabHead, ready: false as const };
	const live = doc.tracking;
	// every change with a result: what is in the model now, then what was tried and where it stands
	const rows = deltaRows(doc.changes, 'log_loss', live).map((d) => {
		const c = doc.changes.find((x) => x.id === d.id)!, inModel = inProduction(c);
		// the Admin area's notes speak to the owner deciding what to release, and point to pages
		// only it has: here a change in the model just says so
		const readyNote = inModel ? 'In the model' : d.readyNote.replace(/: see why on its page$/, '');
		return { ...d, readyNote, inModel };
	});
	return {
		tabHead, ready: true as const, generated: doc.generated_at,
		tiles: scoreTiles(doc),
		version: doc.current?.version ?? null,
		inModel: rows.filter((r) => r.inModel), tried: rows.filter((r) => !r.inModel),
		registered: doc.changes.length,
		example: workedExample(doc.example),
		live: live ? { n: live.n, weeks: live.weeks, start: live.start, to: live.to, tracked: Object.keys(live.changes).length, protocol: live.protocol, matches: live.minimum.matches, minWeeks: live.minimum.weeks } : null
	};
}
