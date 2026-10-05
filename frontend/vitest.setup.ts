import '@testing-library/jest-dom/vitest'
import { beforeEach } from 'vitest'

// Components read and change the real (jsdom) URL through lib/navigation; start every test at the site root.
// (Page tests render .astro files in the node environment, which has no window.)
beforeEach(() => { if (typeof window !== 'undefined') window.history.replaceState(null, '', '/') })
