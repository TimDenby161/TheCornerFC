import { describe, expect, it } from 'vitest';
import { accountError, safePath } from './auth';

describe('safePath', () => {
	it('keeps a path on this site, with its choices', () => {
		expect(safePath('/players?c=39&sort=age')).toBe('/players?c=39&sort=age');
		expect(safePath('/club/42/matches')).toBe('/club/42/matches');
	});
	it('sends anything else home, so a link can\'t bounce a visitor to another site', () => {
		for (const to of [null, '', 'https://evil.example', '//evil.example', '/\\evil.example', 'javascript:alert(1)', '/a b', '/x#<script>'])
			expect(safePath(to)).toBe('/');
	});
});

describe('accountError', () => {
	it('puts known failures in words and says little about the rest', () => {
		expect(accountError({ code: 'invalid_credentials' })).toMatch(/don't match/);
		expect(accountError({ status: 429 })).toMatch(/Too many/);
		expect(accountError({ code: 'something_new' })).toBe('Something went wrong. Try again in a moment.');
		expect(accountError(null)).toBe('Something went wrong. Try again in a moment.');
	});
});
