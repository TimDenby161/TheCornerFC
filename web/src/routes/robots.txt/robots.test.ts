import { describe, expect, it, vi } from 'vitest';

vi.mock('#lib/config.ts', () => ({ SITE_ENV: 'production', SITE_HOST: 'thecornerfc.com' }));
const { GET } = await import('./+server');
const { SEO_BOTS } = await import('#lib/robots.ts');

const robots = async (host: string) => (await GET({ url: new URL(`https://${host}/robots.txt`) } as never)).text();

describe('robots.txt', () => {
	it('asks the SEO tools to stay away and lets search engines in, at the live address', async () => {
		const text = await robots('thecornerfc.com');
		for (const bot of SEO_BOTS) expect(text).toContain(`User-agent: ${bot}\nDisallow: /\n`);
		expect(text).toMatch(/User-agent: \*\nDisallow: \/account/);
		expect(text).not.toMatch(/User-agent: \*\nDisallow: \/\n/);
		expect(text).toContain('Sitemap: https://thecornerfc.com/sitemap.xml');
		expect(text).not.toMatch(/Googlebot|Bingbot/);
	});
	it('keeps every bot out anywhere else', async () => {
		expect(await robots('elsewhere.example')).toBe('User-agent: *\nDisallow: /\n');
	});
});
