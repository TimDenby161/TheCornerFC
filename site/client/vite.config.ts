import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// The C# site's React parts (audit plan: "React where it earns it"). One file, islands.js, built
// into the site's wwwroot/client: each page part marked data-island="..." is taken over by its
// component, with the props the server wrote into it. Until the switch-over, logic the Svelte site
// already has is imported from web/src/lib, so there is one copy of it.
export default defineConfig({
	plugins: [react()],
	// this folder's tsconfig for every file, the ones imported from web/ too (web's own extends the
	// one svelte-kit sync writes, which a fresh checkout doesn't have)
	tsconfig: 'tsconfig.json',
	// served from /client/, where the fantasy pages' parts are fetched from as they are needed
	base: '/client/',
	build: {
		outDir: '../TheCornerFC.Web/wwwroot/client',
		emptyOutDir: true,
		sourcemap: false,
		rollupOptions: {
			input: 'src/islands.tsx',
			output: { entryFileNames: 'islands.js', chunkFileNames: '[name].js', assetFileNames: '[name][extname]' }
		}
	},
	test: { include: ['src/**/*.test.{ts,tsx}'], environment: 'node' }
});
