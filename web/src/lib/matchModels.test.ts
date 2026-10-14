import { describe, expect, it } from 'vitest';
import { MATCH_MODEL_LABELS, MATCH_MODELS, isMatchModel, otherModel } from './matchModels.ts';

describe('the two match models', () => {
	it('knows the two names and nothing else', () => {
		expect(MATCH_MODELS.every(isMatchModel)).toBe(true);
		for (const bad of ['', 'A18', 'base ', null, undefined, 1]) expect(isMatchModel(bad)).toBe(false);
		expect(Object.keys(MATCH_MODEL_LABELS).sort()).toEqual([...MATCH_MODELS].sort());
	});
	it('offers the one that is not live', () => {
		expect(otherModel('base')).toBe('a18');
		expect(otherModel('a18')).toBe('base');
	});
});
