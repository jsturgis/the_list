import { test as base, expect } from '@playwright/test'

/** "Today" for every test, in Bay Area time; the fixture Shows in e2e/fixtures/data are dated around it. */
export const TODAY = new Date('2026-10-01T12:00:00-07:00')

/** Playwright's `test` with the clock frozen at TODAY, so past Shows drop off the same way every run. */
export const test = base.extend({
  page: async ({ page }, run) => {
    await page.clock.setFixedTime(TODAY)
    await run(page)
  },
})

export { expect }
