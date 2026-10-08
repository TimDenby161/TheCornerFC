import adapter from '@sveltejs/adapter-cloudflare';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter(),
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
					// (a form may go on to Stripe's checkout and its page for managing a subscription)
					'form-action': ['self', 'https://checkout.stripe.com', 'https://billing.stripe.com'],
					'frame-ancestors': ['none']
				}
			}
		})
	],
	// The look is still the old site's stylesheets (docs/assets), and the text pages its own files
	// (docs/*.html), read from where they are until the domain moves to this app, so the two can't
	// drift apart.
	server: { fs: { allow: ['../docs'] } },
	test: { include: ['src/**/*.test.ts'] }
});
