import { clubBase, clubFixtures } from '#lib/server/club.ts';

export async function load({ fetch, params }) {
	const { id, site } = await clubBase(fetch, params.id);
	const { paywall } = await clubFixtures(fetch, site, id);
	return { paywall };
}
