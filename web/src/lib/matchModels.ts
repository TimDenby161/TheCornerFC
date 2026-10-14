// The two match models that run side by side (MC-0029, db/migrations/20261014_challenger_model.sql):
// the switch in the Admin area names the live one, which the site and the paper bets use.
export const MATCH_MODELS = ['base', 'a18'] as const;
export type MatchModelName = (typeof MATCH_MODELS)[number];
export const MATCH_MODEL_LABELS: Record<MatchModelName, string> = {
	base: 'The base model (club rank with movers, new clubs and shots)',
	a18: 'The base model with A18’s boosted trees'
};
export const isMatchModel = (value: unknown): value is MatchModelName => MATCH_MODELS.includes(value as MatchModelName);
// The model the button offers: the one that is not live
export const otherModel = (live: MatchModelName): MatchModelName => (live === 'base' ? 'a18' : 'base');
