import { METRIC_LABELS, deltaRows, inProduction, scoreTiles } from '#lib/changes.ts';
import { fail } from '@sveltejs/kit';
import { matchModel, matchModelCompare, switchMatchModel } from '#lib/server/admin.ts';
import { changesDoc, liveDoc } from '#lib/server/changes.ts';
import { apartRow, isMatchModel, pastRows, scoreRows } from '#lib/matchModels.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';

// The Model Change Tracker: the figures at the top, the model comparison with the switch, and the
// changes not yet in production against the current version. The administrator's only
// (hooks.server.ts, and the database again for the document).
// A18's own record, and the results file of its test on past matches against the released club rank
const A18 = 'MC-0018', A18_PAST = 'experiments/a18_on_release/results.json';

export async function load({ fetch, locals }) {
	const tabHead = { title: 'Model Change Tracker', ...TAB_INFO.changes };
	const [doc, live, model, compare] = await Promise.all([changesDoc(fetch, locals.token), liveDoc(fetch, locals.token), matchModel(fetch, locals.token), matchModelCompare(fetch, locals.token)]);
	if (!doc) return { tabHead, ready: false as const };

	const metric = 'log_loss';
	const tiles = scoreTiles(doc);

	// The model comparison above the switch: the bookmakers, the base model and A18 on A18's test
	// on past matches (its change record) and on the same finished live matches, and where the
	// two models part on the fixtures to come.
	const versus = model ? {
		scores: compare ? scoreRows(compare.finished) : null, start: compare?.start ?? null,
		pastScores: pastRows((doc.changes.find((x) => x.id === A18)?.results ?? []).filter((r) => r.source === A18_PAST)),
		apart: compare ? compare.apart.map(apartRow) : []
	} : null;
	return {
		tabHead, ready: true as const, environment: doc.environment, generated: doc.generated_at, stored: doc.stored, differs: doc.differs,
		tiles, metricLabel: METRIC_LABELS[metric],
		// the table is for deciding what to add, so changes already in production, themselves or
		// inside a release, are left out of it
		deltas: deltaRows(doc.changes.filter((x) => !inProduction(x)), metric, live),
		model, versus,
		live: live ? { n: live.n, weeks: live.weeks, start: live.start, to: live.to, generated: live.generated_at, tracked: Object.keys(live.changes).length, protocol: live.protocol, matches: live.minimum.matches, minWeeks: live.minimum.weeks } : null
	};
}

export const actions = {
	// The switch: which match model the site and the paper bets use, from the next run of the
	// predictions. The database checks the caller is an administrator and logs every switch.
	switch: async ({ request, fetch, locals }) => {
		const live = (await request.formData()).get('live');
		if (!isMatchModel(live)) return fail(400, { message: 'That is not one of the two models.' });
		const model = await switchMatchModel(fetch, locals.token, live);
		if (!model) return fail(403, { message: 'The switch was refused, or is not there yet.' });
		return { switched: model.live };
	}
};
