import { json } from '@sveltejs/kit';
import { predictedXi } from '#lib/depth.ts';
import { markPredicted, spots, type Starter, type XiRow } from '#lib/lineups.ts';
import { FINISHED } from '#lib/matches.ts';
import { decodeEntities } from '#lib/players.ts';
import { clubBase, clubSquad } from '#lib/server/club.ts';
import { askAs } from '#lib/server/database.ts';
import { matchBase, matchWhy } from '#lib/server/match.ts';
import { teamName } from '#lib/site.ts';

// One match's line-ups by team (site_lineups): "xi" predicted, "actual" as started, "prematch" as
// predicted before the team sheet. Not kept between openings: a line-up can change before kick-off.
type Lineups = { locked?: boolean; xi: Record<string, XiRow[]> | null; actual: Record<string, XiRow[]> | null; prematch: Record<string, XiRow[]> | null } | null;

export async function GET({ fetch, params, locals }) {
	const { site, m, paywall } = await matchBase(fetch, params.id, locals.token);
	const headers = { 'cache-control': 'private, no-store' };
	const finished = FINISHED.has(m.status) && m.hg != null;

	// A national match: each side's predicted XI comes with the match's model detail; no player ranks
	if (m.intl) {
		const row = await matchWhy(fetch, m.id, locals.token);
		if (row?.locked) return json({ locked: true }, { headers });
		const side = (id: number) => {
			const rows = row?.why?.xi?.[id];
			return {
				label: teamName(site, id), score: null, kit: null, ranks: false,
				spots: rows?.length ? spots(rows.map(([pid, name, role]) => ({ id: pid, name: decodeEntities(name), label: role, rank: null })), false) : null,
				note: rows?.length ? '' : 'No predicted XI for this team.'
			};
		};
		return json({ sides: [side(m.home), side(m.away)], marked: false, note: "From each side's recent national team matches. Call-ups, injuries and suspensions aren't known before the team sheet." }, { headers });
	}

	const fx = await askAs<Lineups>(fetch, locals.token, 'site_lineups', { p_fixture: m.id }).catch(() => null);
	// predicted line-ups are for subscribers
	if (!finished && (fx?.locked || paywall)) return json({ locked: true }, { headers });
	const exact = (finished ? fx?.actual : fx?.xi) || {};
	const side = async (teamId: number, home: boolean) => {
		const rating = home ? m.home_xi : m.away_xi, recent = home ? m.home_recent_xi : m.away_recent_xi;
		const label = `${teamName(site, teamId)}${rating != null ? ` · rating ${Math.round(rating)}${recent != null ? ` (recent ${Math.round(recent)})` : ''}` : ''}`;
		const base = await clubBase(fetch, String(teamId)).catch(() => null);
		const kit = base && /^[0-9a-f]{6}$/i.test(base.doc?.colors?.[0] ?? '') ? [base.doc!.colors![0], /^[0-9a-f]{6}$/i.test(base.doc!.colors![1] ?? '') ? base.doc!.colors![1] : 'ffffff'] : null;
		const listed = exact[String(teamId)];
		if (listed?.length) {
			const xi: Starter[] = listed.map(([pid, name, pos, rank]) => ({ id: pid, name: decodeEntities(name), label: pos || 'CM', rank }));
			const predicted = finished ? fx?.prematch?.[String(teamId)] : null;
			const hits = predicted?.length ? markPredicted(xi, predicted.map(([pid, name, role, rank]) => [pid, decodeEntities(name), role, rank])) : null;
			return { label, kit, ranks: true, spots: spots(xi), note: '', score: hits == null ? null : { hits, of: xi.length, cls: hits >= 9 ? 'good' : hits >= 7 ? 'ok' : 'poor' } };
		}
		if (finished) return { label, kit, ranks: true, spots: null, score: null, note: 'No actual line-up for this team.' };
		// no stored prediction: the one the squad model gives for a match in this competition
		const xi = base ? predictedXi((await clubSquad(fetch, base, locals.token, m.league)).depth) : null;
		return {
			label, kit, ranks: true, score: null, note: xi ? '' : 'No predicted XI for this team.',
			spots: xi ? spots(xi.map((c) => ({ id: c.p.id, name: c.p.name, label: c.box.label, rank: c.rank, chance: c.chance, mins: c.mins }))) : null
		};
	};
	const sides = await Promise.all([side(m.home, true), side(m.away, false)]);
	return json({ sides, marked: finished && !!fx?.prematch, note: '' }, { headers });
}
