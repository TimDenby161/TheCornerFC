import { defineConfig } from 'vitest/config';

// The logic the C# site's React parts (site/client) import from src/lib, tested on its own.
export default defineConfig({
	test: { include: ['src/**/*.test.ts'], environment: 'node' }
});
