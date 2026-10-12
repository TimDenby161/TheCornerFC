import adapter from '@sveltejs/adapter-cloudflare';
import { sveltekit } from '@sveltejs/kit/vite';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';
import { siteEnvironment } from './src/lib/environments.ts';

// Which copy of the site this builds, production or staging: VITE_SITE_ENV, from the build's
// variables (Cloudflare) or the local settings file scripts/environment.py writes in web/. No
// default: a build that names neither fails here, before anything is built. The unit tests are
// the one exception, and say production themselves.
export default defineConfig(({ mode }) => {
	// (what the build was started with comes before the local settings file)
	const given = loadEnv(mode, '.', ['VITE_', 'WORKERS_CI_']);
	const site = siteEnvironment(mode === 'test' ? 'production' : given.VITE_SITE_ENV);
	const database = site.url as `https://${string}.supabase.co`;
	return {
	// the commit being built (Cloudflare's build names it), for /version
	define: { __COMMIT__: JSON.stringify(given.WORKERS_CI_COMMIT_SHA || 'local') },
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// (the local stand-in for the Worker takes the same environment's settings from wrangler.jsonc)
			adapter: adapter({ platformProxy: { environment: site.name === 'staging' ? 'staging' : undefined } }),
			// What a page may load and run, sent as a header with every page (the old site's policy,
			// tightened where a server allows it). Scripts: this site's own files, the one the server
			// writes into the page (named by a one-off nonce), and Cloudflare's bot check. No inline
			// styles, nothing framed by another site, and the browser talks to this server only: the
			// database is asked from the server.
			csp: {
				mode: 'nonce',
				directives: {
					'default-src': ['self'],
					'script-src': ['self', 'https://challenges.cloudflare.com'],
					'frame-src': ['https://challenges.cloudflare.com'],
					// the one inline style let through, by its hash, is the framework's own: the hidden line
					// that tells a screen reader which page a link has opened
					'style-src': ['self', 'unsafe-hashes', 'sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo='],
					'img-src': ['self', 'https://flagcdn.com'],
					'connect-src': ['self'],
					'manifest-src': ['self'],
					'object-src': ['none'],
					'base-uri': ['self'],
					// (a form may go on to Google's sign-in by way of the sign-in service, and to Stripe's checkout
					// and its page for managing a subscription)
					'form-action': ['self', database, 'https://accounts.google.com', 'https://checkout.stripe.com', 'https://billing.stripe.com'],
					'frame-ancestors': ['none']
				}
			}
		})
	],
	test: { include: ['src/**/*.test.ts'], env: { VITE_SITE_ENV: 'production' } }
	};
});
