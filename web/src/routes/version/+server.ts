import { json } from '@sveltejs/kit';
import { SITE } from '#lib/config.ts';

// Which copy of the site answered, the commit it was built from and the database it reads: what
// the staging check and a promotion read to know what is really deployed (guide/environments.md).
// Nothing secret: the project's id is in every page's requests already.
export function GET() {
	return json({ environment: SITE.name, commit: __COMMIT__, project: SITE.project }, { headers: { 'cache-control': 'no-store' } });
}
