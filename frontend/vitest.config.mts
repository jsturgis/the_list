/// <reference types="vitest/config" />
import { getViteConfig } from 'astro/config'

// Astro's Vite config, so tests resolve imports, React and import.meta.env (BASE_URL, PUBLIC_*) as the site does.
export default getViteConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['**/__tests__/**/*.test.{ts,tsx}'],
  },
})
