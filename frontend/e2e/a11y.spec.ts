import AxeBuilder from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

// Accessibility checks with axe on every page and state, in light and dark mode. Any serious or critical
// violation of WCAG 2.1 A/AA fails the test. Fix violations rather than disabling rules; a disabled rule needs a
// written reason here.

/** [name, path, how to get the page into the state to check] */
const STATES: [string, string, (page: Page) => Promise<void>][] = [
  // The Oct 10 Show carries every flag, so each badge colour is checked.
  ['home', './', page => expect(page.getByText('Will Sell Out')).toBeVisible()],
  ['home with filters and Advanced filters open', './?region=sf&genre=indie&fromDate=2026-10-01&priceMax=40&age=21%2B', async page => {
    await expect(page.locator('main [data-show-link]').first()).toBeVisible()
    await expect(page.getByLabel('From date')).toBeVisible()  // Advanced filters open when the URL has one
  }],
  ['Setup Alert panel open', './?region=east_bay', async page => {
    await page.getByRole('button', { name: /setup alert/i }).click()
    await expect(page.getByLabel('Email')).toBeVisible()
  }],
  ['Show page', 'shows/102/', page => expect(page.getByRole('heading', { name: 'Lineup' })).toBeVisible()],
  ['Band page', 'bands/1/', page => expect(page.getByTestId('similar-bands')).toBeVisible()],
  ['Band page with SoundCloud and Bandcamp', 'bands/7/', page => expect(page.getByRole('link', { name: /bandcamp/i })).toBeVisible()],
  ['Show page, Cancelled', 'shows/107/', page => expect(page.getByText('Cancelled')).toBeVisible()],
  ['Show page, Postponed', 'shows/108/', page => expect(page.getByText('Postponed')).toBeVisible()],
  ['Venue page', 'venues/2/', page => expect(page.getByRole('heading', { name: 'Upcoming Shows' })).toBeVisible()],
  ['not-found page', 'shows/99999/', page => expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()],
  ['Alerts page, signed out', 'alerts/', page => expect(page.getByRole('button', { name: /sign-in link/i })).toBeVisible()],
  ['Unsubscribe page', 'alerts/unsubscribe/', page => expect(page.getByRole('heading', { level: 1 })).toBeVisible()],
]

for (const scheme of ['light', 'dark'] as const) {
  test.describe(`accessibility, ${scheme} mode`, () => {
    test.use({ colorScheme: scheme })

    for (const [name, path, ready] of STATES) {
      test(name, async ({ page }) => {
        await page.goto(path)
        await ready(page)
        const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
        const blocking = violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
        const report = blocking.map(v =>
          `${v.impact}: ${v.id} (${v.help})\n` + v.nodes.map(n => `  ${n.target.join(' ')}\n    ${n.failureSummary?.replace(/\n/g, '\n    ')}`).join('\n'))
        expect(report, report.join('\n\n')).toEqual([])
      })
    }
  })
}
