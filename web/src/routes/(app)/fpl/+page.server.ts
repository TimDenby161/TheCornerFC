import { findingsView, type FplFindings } from '#lib/fplFindings.ts';
import { keptDocOrNull } from '#lib/server/database.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';

// The page is the site owner's: a visitor who isn't signed in is sent nothing but the way in. The
// findings hold no FPL data (they are the model's own test results); the predictions, which do,
// are never written here: the owner's browser asks for them (/fantasy/data).
export async function load({ fetch, locals }) {
	const base = { tabHead: { title: 'FPL', ...TAB_INFO.fpl } };
	if (!locals.user) return { ...base, findings: null };
	const doc = await keptDocOrNull<FplFindings>(fetch, 'fpl', 300_000).catch(() => null);
	return { ...base, findings: doc ? findingsView(doc) : null };
}
