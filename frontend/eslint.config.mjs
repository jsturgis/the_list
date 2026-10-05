import { defineConfig, globalIgnores } from 'eslint/config'
import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'
import astro from 'eslint-plugin-astro'
import globals from 'globals'

export default defineConfig([
  globalIgnores([
    'dist/**',
    '.astro/**',
    // Playwright: the built fixture site and run output
    'e2e/.site/**',
    'playwright-report/**',
    'test-results/**',
  ]),
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    extends: [reactHooks.configs.flat['recommended-latest']],
  },
  astro.configs.recommended,
  { languageOptions: { globals: { ...globals.browser, ...globals.node } } },
])
