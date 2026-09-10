import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    globals: true,
    exclude: ['node_modules/**', 'dist/**', 'tests/playwright/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json-summary'],
      // Run via `npm run test:coverage:auth`, which passes the matching test
      // files. Instrumenting the whole suite spins up 76 jsdom environments
      // and takes ~10 minutes (workers start timing out), so coverage is
      // deliberately a scoped, separate command rather than part of
      // `npm test`. The thresholds below apply to whatever run enables
      // --coverage, so a run that does not exercise these files will fail
      // them — that is intended, to stop a partial run reporting success.
      // Scoped to the auth surface rather than all of src/. A repo-wide
      // number here would be dominated by pages with no tests and would
      // tell you nothing about whether the security-critical code is
      // covered — which is the question this exists to answer. Widen the
      // include list when a module gets real coverage, not before.
      include: [
        'src/lib/authToken.js',
        'src/lib/authStorage.js',
      ],
      thresholds: {
        // The auth token/storage layer is where a silent regression turns
        // into "everyone is logged out" or "the token is readable again",
        // so it is held at 100%. Phase L3.
        'src/lib/authToken.js': {
          statements: 100,
          branches: 100,
          functions: 100,
          lines: 100,
        },
        'src/lib/authStorage.js': {
          statements: 100,
          branches: 100,
          functions: 100,
          lines: 100,
        },
      },
    },
  },
})
