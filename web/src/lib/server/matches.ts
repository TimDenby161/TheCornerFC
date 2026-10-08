import { FINISHED, LIVE, NO_GAME, type Match } from '#lib/matches.ts';
import { reasonText, shownProbs } from '#lib/matchday.ts';
import { pageHref } from '#lib/menu.ts';
import type { Club } from '#lib/rankings.ts';
import { teamName, type Site } from '#lib/site.ts';

const RATING_LABELS: Record<number, string> = { 1: 'Terrible', 2: 'Poor', 3: 'Decent', 4: 'Very good', 5: 'Excellent' };
const FACTORS = [['r_winner', 'Winner', '30%'], ['r_margin', 'Margin', '25%'], ['r_clean_sheets', 'Clean sheets', '20%'], ['r_shape', 'Shape', '15%'], ['r_goals', 'Goals', '10%']] as const;

// A match as its card draws it: names, the strengths beside them, the chances as the bars show
// them, the key reasons in words, and what (if anything) the database held back for subscribers.
export type CardView = ReturnType<typeof cardView>;
export function cardView(site: Site, ranks: Map<number, Club>, m: Match, paywall: boolean) {
	const finished = FINISHED.has(m.status) && m.hg != null;
	const upcoming = !finished && !LIVE.has(m.status);
	const intl = !!m.intl;
	const side = (id: number, rankThen: number | null) => {
		const name = teamName(site, id);
		return {
			id, name, nation: intl, href: intl ? pageHref('nation', site.nation_pages?.[id] || name) : undefined,
			// a finished match: the strength going into it; otherwise the club's strength now
			rank: finished ? rankThen : ranks.get(id)?.current ?? rankThen
		};
	};
	const home = side(m.home, m.home_rank), away = side(m.away, m.away_rank);
	const probs = m.p_home != null && m.p_draw != null ? shownProbs(m.p_home, m.p_draw) : null;
	const market = m.m_home != null && m.m_draw != null && probs ? shownProbs(m.m_home, m.m_draw) : null;
	// behind the paywall: the database left the paid fields of a match to come out for this visitor
	const locked = paywall && upcoming && !NO_GAME.has(m.status);
	return {
		id: m.id, kickoff: m.kickoff, round: m.round, status: m.status, intl,
		home, away, hg: m.hg, ag: m.ag, penH: m.pen_h, penA: m.pen_a, homeXg: m.home_xg, awayXg: m.away_xg, likely: m.likely, source: m.source,
		finished, upcoming, probs, market,
		tag: LIVE.has(m.status) ? 'Live' : m.status === 'PST' ? 'Postponed' : m.status === 'CANC' ? 'Cancelled' : m.status === 'ABD' ? 'Abandoned' : FINISHED.has(m.status) ? m.status : '',
		live: LIVE.has(m.status),
		lock: !locked ? null : probs ? 'depth' as const : 'chances' as const,
		// what opens from the card: the line-ups (not while it is being played, nor for a national
		// match once played, which has a predicted XI only) and the model's detail
		canLineups: !locked && !LIVE.has(m.status) && !NO_GAME.has(m.status) && (!intl || (!finished && !!probs)),
		canDetail: !locked && !!probs,
		// both clubs' expected squads, asked for when the card comes into view
		canSquads: upcoming && !intl && !locked && !NO_GAME.has(m.status),
		reasons: upcoming && probs ? (m.reasons || []).flatMap(([k, v]) => reasonText(k, v, home.name, away.name) ?? []) : [],
		// how the prediction did, once it's over
		rating: finished && m.rating ? {
			score: m.rating, label: RATING_LABELS[m.rating],
			factors: FACTORS.map(([k, label, weight]) => ({ label, weight, score: m[k] }))
		} : null
	};
}
