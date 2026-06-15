import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

// Standalone unit-test config for the frontend's PURE logic modules
// (utils/*, viewspec/*). Deliberately does NOT load the sveltekit() plugin —
// these tests exercise renderer-agnostic functions with no DOM or SvelteKit
// runtime, so a plain node environment + the $lib alias is all they need.
export default defineConfig({
	resolve: {
		alias: {
			$lib: fileURLToPath(new URL('./src/lib', import.meta.url)),
		},
	},
	test: {
		environment: 'node',
		include: ['src/**/*.test.ts'],
	},
});
