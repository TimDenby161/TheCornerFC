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
			adapter: adapter()
		})
	],
	// The look is still the old site's stylesheets (docs/assets), and the text pages its own files
	// (docs/*.html), read from where they are until the domain moves to this app, so the two can't
	// drift apart.
	server: { fs: { allow: ['../docs'] } },
	test: { include: ['src/**/*.test.ts'] }
});
