import '@testing-library/jest-dom/vitest'
import { beforeEach } from 'vitest'

// Components read and change the real (jsdom) URL through lib/navigation; start every test at the site root.
beforeEach(() => window.history.replaceState(null, '', '/'))
