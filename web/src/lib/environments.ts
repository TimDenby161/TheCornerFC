// The two copies of the site, and which database each reads (guide/environments.md). Nothing
// here is secret: a project's id and its publishable key only identify it, and the database
// decides what the key may do. The Python jobs name the same projects (PROJECTS in
// thecornerfc/config.py); a test holds the two lists together.
//
// A build must say which it is, with VITE_SITE_ENV. There is no default: a build that names
// neither, or names staging before its project is recorded here, fails.
export const ENVIRONMENTS = {
	production: {
		project: 'bookkurhdabdeccckjbn',
		key: 'sb_publishable_JZ_oJVHIO75SFbFc95LQew_3wmKuvM7',
		host: 'thecornerfc.com',
		// Cloudflare Turnstile's site key for thecornerfc.com
		botCheck: '0x4AAAAAAFQgIiqxiuE9dqIM'
	},
	staging: {
		project: 'sjvzmlbdowebylnzvisa',
		key: 'sb_publishable_eLnEE_9Qx_BLV4kWpSQACA_-xn1YXNj',
		host: 'staging.thecornerfc.com',
		// Turnstile's published test key, which always passes: staging has no widget of its own
		botCheck: '1x00000000000000000000AA'
	}
} as const;

export type SiteEnv = keyof typeof ENVIRONMENTS;

export function siteEnvironment(name: unknown) {
	if (name !== 'production' && name !== 'staging')
		throw new Error(`VITE_SITE_ENV must be "production" or "staging" (it is ${name === undefined || name === '' ? 'not set' : JSON.stringify(name)}): run python scripts/environment.py, or set it in the build's variables`);
	const env = ENVIRONMENTS[name];
	if (!env.project || !env.key) throw new Error(`The ${name} project is not recorded yet (web/src/lib/environments.ts)`);
	return { name: name as SiteEnv, ...env, url: `https://${env.project}.supabase.co` };
}
