import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

// iOS Safari zooms the page in when a focused field's text is under 16px (DESIGN.md, section 4). Every text entry
// control on the site is at least 16px, so it never does; the viewport still allows pinch zoom.

/** [name, path, how to get the page into the state to check, how many fields it should have at least] */
const STATES: [string, string, (page: Page) => Promise<void>, number][] = [
  // Advanced filters open when the URL has one, so every filter bar field is on screen.
  ['home filter bar, with Advanced filters', './?fromDate=2026-10-01', page => expect(page.getByLabel('From date')).toBeVisible(), 7],
  ['Save search panel', './?region=east_bay', async page => {
    await page.getByRole('button', { name: /save search/i }).click()
    await expect(page.getByLabel('Email')).toBeVisible()
  }, 2],
  ['Band page, alert bell panel', 'bands/3/', async page => {
    await page.getByRole('button', { name: 'Get alerts for Static Bloom' }).click()
    await expect(page.getByLabel('Email')).toBeVisible()
  }, 1],
  ['Alerts page, signed out', 'alerts/', page => expect(page.getByRole('button', { name: /sign-in link/i })).toBeVisible(), 1],
]

test.use({ viewport: { width: 390, height: 844 } })

for (const [name, path, ready, least] of STATES) {
  test(`form fields are at least 16px, so iOS doesn't zoom: ${name}`, async ({ page }) => {
    await page.goto(path)
    await ready(page)
    const fields = await page.locator('input, select, textarea').evaluateAll(els =>
      els
        .filter(el => !['checkbox', 'radio', 'button', 'submit', 'reset', 'hidden', 'image', 'range', 'color'].includes((el as HTMLInputElement).type))
        .filter(el => (el as HTMLElement).offsetParent !== null)
        .map(el => ({
          field: el.id || el.getAttribute('aria-label') || el.outerHTML.slice(0, 80),
          px: parseFloat(getComputedStyle(el).fontSize),
        })))
    expect(fields.length).toBeGreaterThanOrEqual(least)
    expect(fields.filter(f => f.px < 16), 'fields under 16px').toEqual([])
  })
}
