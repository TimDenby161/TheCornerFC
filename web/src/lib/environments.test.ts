import { describe, expect, it } from 'vitest';
import { ENVIRONMENTS, siteEnvironment } from './environments.ts';

describe('which copy of the site a build is', () => {
	it('has no default: a build that names neither environment fails', () => {
		for (const name of [undefined, '', 'prod', 'Production', 'STAGING', 'development', null, 1])
			expect(() => siteEnvironment(name)).toThrow(/VITE_SITE_ENV/);
	});
	it('gives production the live project and address', () => {
		const p = siteEnvironment('production');
		expect([p.name, p.host, p.url]).toEqual(['production', 'thecornerfc.com', 'https://bookkurhdabdeccckjbn.supabase.co']);
	});
	it("keeps the two apart: staging never has production's project, key, address or bot-check key", () => {
		const { production, staging } = ENVIRONMENTS;
		for (const k of ['project', 'key', 'host', 'botCheck'] as const) expect(staging[k]).not.toBe(production[k]);
		expect(staging.host.endsWith('.thecornerfc.com')).toBe(true);
	});
	it('fails a staging build until the staging project is recorded, and never falls back to production', () => {
		if (ENVIRONMENTS.staging.project && ENVIRONMENTS.staging.key) expect(siteEnvironment('staging').url).toBe(`https://${ENVIRONMENTS.staging.project}.supabase.co`);
		else expect(() => siteEnvironment('staging')).toThrow(/not recorded/);
	});
});

