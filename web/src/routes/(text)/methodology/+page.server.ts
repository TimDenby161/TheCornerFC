import { keptDoc } from '#lib/server/database.ts';

// The live figures on the page: how fresh the data is, the scored match predictions and
// line-ups, and the model version in use
type Scored = { n: number; period?: { from: string; to: string }; versions?: { name: string; n: number }[] };
export type Methodology = {
	generated_at: string;
	freshness?: { predictions?: string; injuries?: string; odds?: string; model?: { name: string; code?: string; registered?: string } };
	matches?: (Scored & { accuracy: number; log_loss: number; brier: number; exact_score?: { n: number; accuracy: number }; calibration: [string, number, number, number][]; excluded_no_regulation_score?: number }) | null;
	lineups?: (Scored & { correct_starters_mean: number; role_accuracy?: { n: number; accuracy: number }; excluded_no_official_xi?: number }) | null;
};

export async function load({ fetch, setHeaders }) {
	setHeaders({ 'cache-control': 'public, max-age=60' });
	return { live: await keptDoc<Methodology>(fetch, 'methodology', 300_000).catch(() => null), now: Date.now() };
}
