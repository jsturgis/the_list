import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

// Smoke tests of the static site built from e2e/fixtures/data, with "today" frozen at 2026-10-01.
// Upcoming fixture Shows: 102 (Pick) and 103 on Oct 3, 104 (free) Oct 4, 105 Oct 5, 106 Oct 10.
// Show 101 (Ghost of Yesterday) is dated Sep 28, so it's past and never listed.

/** The Show cards on the home page, in page order. */
const showCards = (page: Page) => page.locator('main a[href*="/shows/"]')

const headliner = (page: Page, name: string) => page.getByRole('heading', { level: 3, name })

test('home page lists the upcoming Shows', async ({ page }) => {
  await page.goto('./')

  await expect(page).toHaveTitle(/The List/)
  await expect(page.getByRole('heading', { level: 1, name: "This Week's Shows" })).toBeVisible()
  await expect(page.getByText('Bay Area & Santa Cruz Concert Events — Sep 25, 2026')).toBeVisible()
  await expect(page.getByText('Showing 5 of 5 shows')).toBeVisible()
  await expect(showCards(page)).toHaveCount(5)

  // Steve's Pick comes first within its date, ahead of the earlier door time.
  await expect(showCards(page).first()).toContainText("Steve's pick")
  await expect(showCards(page).first()).toContainText('Neon Harbor')
  await expect(showCards(page).nth(1)).toContainText('Gilman Youth')

  await expect(headliner(page, 'Ghost of Yesterday')).toHaveCount(0)
  await expect(page.getByRole('main').getByRole('alert')).toHaveCount(0)
})

test('search narrows the list by band or venue, and Clear filters resets it', async ({ page }) => {
  await page.goto('./')
  await expect(showCards(page)).toHaveCount(5)

  // A typo still matches (fuzzy search); Neon Harbor headlines two Shows.
  await page.getByLabel('Search').fill('neon harbr')
  await expect(page).toHaveURL(/[?&]q=neon\+harbr/)
  await expect(showCards(page)).toHaveCount(2)
  await expect(page.getByText('Showing 2 of 5 shows')).toBeVisible()

  // A venue name works too.
  await page.getByLabel('Search').fill('gilman')
  await expect(showCards(page)).toHaveCount(2)
  await expect(headliner(page, 'Gilman Youth')).toBeVisible()

  await page.getByRole('button', { name: 'Clear filters' }).click()
  await expect(showCards(page)).toHaveCount(5)
  await expect(page.getByLabel('Search')).toHaveValue('')
  await expect(page).not.toHaveURL(/q=/)
})

test('region and free filters update the URL and survive a reload', async ({ page }) => {
  await page.goto('./')

  await page.getByLabel('Region').selectOption({ label: 'East Bay' })
  await expect(page).toHaveURL(/[?&]region=east_bay/)
  await expect(showCards(page)).toHaveCount(2)

  await page.getByLabel('Region').selectOption({ label: 'All Regions' })
  await expect(page).not.toHaveURL(/region=/)
  // The checkbox follows the URL, which updates asynchronously, so click() rather than check().
  await page.getByLabel('Free only').click()
  await expect(page).toHaveURL(/[?&]free=1/)
  await expect(page.getByLabel('Free only')).toBeChecked()
  await expect(showCards(page)).toHaveCount(1)
  await expect(headliner(page, 'Tidepool Choir')).toBeVisible()

  await page.reload()
  await expect(page.getByLabel('Free only')).toBeChecked()
  await expect(showCards(page)).toHaveCount(1)
})

test('a Show card opens the Show page', async ({ page }) => {
  await page.goto('./')
  await showCards(page).first().click()

  await expect(page).toHaveURL(/\/the_list\/shows\/102\/$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Neon Harbor' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Lineup' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Venue' })).toBeVisible()
  await expect(page.getByTestId('act-name')).toHaveText(['Neon Harbor', 'Static Bloom'])
  await expect(page.getByRole('link', { name: 'Add to calendar' })).toBeVisible()
})

test('a Band link opens the Band page', async ({ page }) => {
  await page.goto('shows/102/')
  await page.getByTestId('act-name').filter({ hasText: 'Neon Harbor' }).click()

  await expect(page).toHaveURL(/\/the_list\/bands\/1\/$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Neon Harbor' })).toBeVisible()
  await expect(page.getByTestId('similar-bands')).toContainText('Fog City Ramblers')
  await expect(page.getByRole('dialog')).toHaveCount(0)

  await page.goBack()
  await expect(page).toHaveURL(/\/the_list\/shows\/102\/$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Neon Harbor' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Lineup' })).toBeVisible()
})

test('a Band URL loaded directly renders the full Band page', async ({ page }) => {
  await page.goto('bands/1/')

  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 1, name: 'Neon Harbor' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Upcoming Shows' })).toBeVisible()
  await expect(page.getByTestId('similar-bands')).toContainText('Static Bloom')
})

test('the Venue link opens the Venue page with its upcoming Shows', async ({ page }) => {
  await page.goto('shows/103/')
  await page.getByRole('main').getByRole('link', { name: '924 Gilman Street' }).first().click()

  await expect(page).toHaveURL(/\/the_list\/venues\/2\/$/)
  await expect(page.getByRole('heading', { level: 1, name: '924 Gilman Street' })).toBeVisible()
  const upcoming = page.getByRole('region', { name: 'Upcoming Shows' })
  await expect(upcoming.locator('a[href*="/shows/"]')).toHaveCount(2)
})

test('an unknown page shows the 404 page', async ({ page }) => {
  await page.goto('shows/99999/')

  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
  await page.getByRole('link', { name: "See this week's shows" }).click()
  await expect(page.getByRole('heading', { level: 1, name: "This Week's Shows" })).toBeVisible()
})

test('a failed data load shows an error', async ({ page }) => {
  await page.route('**/data/shows.json', route => route.fulfill({ status: 500 }))
  await page.goto('./')

  await expect(page.getByRole('main').getByRole('alert')).toContainText("Couldn't load the list of shows")
})
