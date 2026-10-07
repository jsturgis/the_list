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

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test("a Band page's alert panel spans the column and stays on screen", async ({ page }) => {
    await page.goto('bands/3/')
    await page.getByRole('button', { name: 'Get alerts for Static Bloom' }).click()
    const panel = (await page.locator('form:has(input[type=email])').boundingBox())!
    const column = (await page.getByRole('heading', { level: 1 }).locator('xpath=ancestor::*[parent::main][1]').boundingBox())!
    expect(Math.round(panel.x)).toBe(Math.round(column.x))
    expect(Math.round(panel.width)).toBe(Math.round(column.width))
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390)  // no sideways scroll
  })

  test('the Save search panel spans the filter bar and stays on screen', async ({ page }) => {
    await page.goto('./?region=east_bay')
    await page.getByRole('button', { name: /save search/i }).click()
    const panel = (await page.locator('form:has(#save-filter-name)').boundingBox())!
    // The filter bar's last row, where the button sits.
    const bar = (await page.getByRole('button', { name: /save search/i }).locator('xpath=ancestor::div[contains(@class, "border-t")][1]').boundingBox())!
    expect(Math.round(panel.x)).toBe(Math.round(bar.x))
    expect(Math.round(panel.width)).toBe(Math.round(bar.width))
    expect(panel.x).toBeGreaterThanOrEqual(0)
    expect(panel.x + panel.width).toBeLessThanOrEqual(390)
  })
})

test("a Band page's bell offers alerts for that Band; its link lists only that Band's Shows", async ({ page }) => {
  let redirect = ''
  await page.route('https://e2e.invalid/auth/v1/otp**', async route => {
    redirect = new URL(route.request().url()).searchParams.get('redirect_to') ?? ''
    await route.fulfill({ json: {} })
  })
  await page.goto('bands/3/')
  const bell = page.getByRole('button', { name: 'Get alerts for Static Bloom' })
  await bell.click()
  await page.getByLabel('Email').fill('fan@example.com')
  await page.getByRole('button', { name: /email me a sign-in link/i }).click()
  await expect(page.getByText('Check your email for a sign-in link')).toBeVisible()
  expect(new URL(redirect).searchParams.get('save')).toBe('bandId=3')  // the Alerts page saves it after sign-in

  await page.goto('./?bandId=3')
  await expect(page.getByText('Shows with')).toBeVisible()
  await expect(page.getByRole('main').getByText('Static Bloom').first()).toBeVisible()
  const rows = page.locator('main [data-show-link]')
  await expect(rows).not.toHaveCount(0)
  for (const row of await rows.all()) await expect(row.locator('xpath=ancestor::div[contains(@class,"relative")][1]')).toContainText('Static Bloom')
})

for (const [label, width] of [['desktop', 1280], ['phone', 390]] as const) {
  test(`the alert bell stays centred on a long title's first line (${label})`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 })
    await page.goto('bands/3/')
    const title = page.getByRole('heading', { level: 1 })
    await title.evaluate(h => { h.textContent = 'Static Bloom and the Extremely Long Band Name That Wraps Onto Several Lines' })
    const bell = page.getByRole('button', { name: /^Get alerts for / })
    const t = (await title.boundingBox())!, b = (await bell.boundingBox())!
    const line = parseFloat(await title.evaluate(h => getComputedStyle(h).lineHeight))
    expect(t.height).toBeGreaterThan(line * 1.5)                                // the title did wrap
    expect(Math.abs(b.y + b.height / 2 - (t.y + line / 2))).toBeLessThanOrEqual(1)  // centred on line one
    expect(b.x).toBeGreaterThan(t.x + t.width)                                   // still beside it, at the right
  })
}

for (const [label, width] of [['desktop', 1280], ['phone', 390]] as const) {
  test(`Venue and Band rows centre the compact date in the row (${label})`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    for (const path of ['venues/2/', 'bands/1/']) {
      await page.goto(path)
      const rows = await page.getByRole('region', { name: 'Upcoming Shows' }).getByRole('listitem').all()
      expect(rows.length).toBeGreaterThan(0)
      for (const row of rows) {
        const box = (await row.boundingBox())!
        const date = (await row.locator('time').boundingBox())!
        expect(Math.abs((date.y + date.height / 2) - (box.y + box.height / 2)), path).toBeLessThanOrEqual(1)
      }
    }
  })
}

test("a Band's stored photo loads from the site, under its base path", async ({ page }) => {
  await page.goto('bands/1/')
  const photo = page.getByRole('img', { name: 'Neon Harbor' })
  await expect(photo).toHaveAttribute('src', /^\/the_list\/images\/bands\/1-[0-9a-f]{10}\.webp$/)
  await expect.poll(() => photo.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBeGreaterThan(0)
  // A Wikimedia Commons photo carries its credit.
  await expect(page.getByRole('figure')).toContainText('Photo: S. Bollmann, CC BY-SA 4.0, via Wikimedia Commons')
  // A Discogs photo says so.
  await page.goto('bands/7/')
  await expect(page.getByRole('figure')).toHaveText('Photo via Discogs')
})

const LONG_NAME = 'Neon Harbor and the Extremely Long Band Name That Wraps Onto Several Lines'

for (const name of ['Neon Harbor', LONG_NAME]) {
  test(`on phones a Band's photo is a circle left of its name, centred on it, credited below (${name.length} chars)`, async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 })
    await page.goto('bands/1/')
    const title = page.getByRole('heading', { level: 1 })
    if (name !== 'Neon Harbor') await title.evaluate((h, n) => { h.textContent = n }, name)
    const photo = page.getByRole('img', { name: 'Neon Harbor' })
    await expect(photo).toBeVisible()
    const p = (await photo.boundingBox())!, t = (await title.boundingBox())!
    const radius = parseFloat(await photo.evaluate(img => getComputedStyle(img).borderTopLeftRadius))
    expect(Math.abs(p.width - p.height)).toBeLessThanOrEqual(0.5)             // square…
    expect(radius).toBeGreaterThanOrEqual(p.width / 2)                       // …and round
    expect(p.width).toBeGreaterThanOrEqual(56)
    expect(p.width).toBeLessThanOrEqual(72)
    expect(p.x + p.width).toBeLessThan(t.x)                                  // left of the name
    expect(Math.abs((p.y + p.height / 2) - (t.y + t.height / 2))).toBeLessThanOrEqual(2)  // centred on it
    if (name !== 'Neon Harbor') expect(t.height).toBeGreaterThan(p.height)  // the long name did wrap
    // The credit stays visible, on its own line under the photo and name.
    const credit = page.getByRole('figure').locator('figcaption')
    await expect(credit).toBeVisible()
    await expect(credit.getByRole('link', { name: 'Wikimedia Commons' })).toBeVisible()
    const c = (await credit.boundingBox())!
    expect(c.y).toBeGreaterThanOrEqual(Math.max(p.y + p.height, t.y + t.height))
    // The bell stays centred on the name's first line.
    const bell = (await page.getByRole('button', { name: /^Get alerts for / }).boundingBox())!
    const line = parseFloat(await title.evaluate(h => getComputedStyle(h).lineHeight))
    expect(Math.abs(bell.y + bell.height / 2 - (t.y + line / 2))).toBeLessThanOrEqual(1)
  })
}

test('on phones a Discogs photo keeps its credit, and a Band without a photo has no picture', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 })
  await page.goto('bands/7/')
  await expect(page.getByRole('figure').locator('figcaption')).toBeVisible()
  await expect(page.getByRole('figure').getByRole('link', { name: 'Discogs' })).toBeVisible()
  await page.goto('bands/3/')
  await expect(page.getByRole('heading', { level: 1, name: 'Static Bloom' })).toBeVisible()
  await expect(page.locator('main header img')).toHaveCount(0)
  await expect(page.getByRole('figure')).toHaveCount(0)
})

test("on desktop a Band's photo spans the column above its name, credited under it", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('bands/1/')
  const photo = page.getByRole('img', { name: 'Neon Harbor' })
  await expect.poll(() => photo.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBeGreaterThan(0)
  const p = (await photo.boundingBox())!, t = (await page.getByRole('heading', { level: 1 }).boundingBox())!
  const c = (await page.getByRole('figure').locator('figcaption').boundingBox())!
  expect(p.width).toBe(672)                         // the narrow column's width
  expect(p.x).toBe(t.x)
  expect(p.y + p.height).toBeLessThanOrEqual(c.y)   // photo, then credit, then name
  expect(c.y + c.height).toBeLessThan(t.y)
  expect(await photo.evaluate(img => getComputedStyle(img).borderTopLeftRadius)).toBe('8px')
})

for (const scheme of ['light', 'dark'] as const) {
  test(`a Band's listening links are logo buttons, 44px or more, that fit a phone (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await page.setViewportSize({ width: 320, height: 800 })
    await page.goto('bands/1/')
    const buttons = page.getByRole('link', { name: /^Listen on / })
    await expect(buttons).toHaveCount(6)
    for (const button of await buttons.all()) {
      const box = await button.boundingBox()
      expect(box!.width).toBeGreaterThanOrEqual(44)
      expect(box!.height).toBeGreaterThanOrEqual(44)
    }
    // Qobuz's wordmark is an image under the base path: the white one in dark mode.
    const qobuz = page.getByRole('link', { name: 'Listen on Qobuz (subscription)' }).locator('img')
    await expect.poll(() => qobuz.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBeGreaterThan(0)
    expect(await qobuz.evaluate((img: HTMLImageElement) => new URL(img.currentSrc).pathname)).toBe(`/the_list/icons/qobuz-${scheme}.png`)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  })
}

test('a listening service without a logo keeps a labelled button beside the logo buttons', async ({ page }) => {
  await page.goto('bands/7/')
  await expect(page.getByRole('link', { name: /^Listen on / })).toHaveText(['', '', ''])
  await expect(page.getByRole('link', { name: 'Listen on Bandcamp' })).toHaveAttribute('href', 'https://redwoodsirens.bandcamp.com')
  await expect(page.getByRole('link', { name: 'Listen on SoundCloud' })).toHaveAttribute('href', 'https://soundcloud.com/redwood-sirens')
  await expect(page.getByRole('link', { name: 'Listen on Deezer' })).toHaveAttribute('href', 'https://www.deezer.com/artist/7')
  await expect(page.getByRole('link', { name: 'Amazon Music' })).toHaveText('Amazon Music')
  await expect(page.getByRole('link', { name: 'Amazon Music' })).toHaveAttribute('title', 'Amazon Music (subscription)')
})

test("a Venue page has a bell for that Venue's alerts", async ({ page }) => {
  await page.goto('venues/2/')
  await expect(page.getByRole('button', { name: /^Get alerts for / })).toBeVisible()
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
  await page.route('**/home-shows.json', route => route.fulfill({ status: 500 }))
  await page.goto('./')

  await expect(page.getByRole('main').getByRole('alert')).toContainText("Couldn't load the list of shows")
})

test("a Venue's Upcoming Shows still show if the page script fails to load", async ({ page }) => {
  await page.route('**/_astro/*.js', route => route.abort())
  await page.goto('venues/2/')

  const upcoming = page.getByRole('region', { name: 'Upcoming Shows' })
  await expect(upcoming).toBeVisible()
  await expect(upcoming.locator('a[href*="/shows/"]')).toHaveCount(2)
})

test("a Band's Upcoming Shows still show if the page script throws", async ({ page }) => {
  await page.route('**/_astro/*.js', route =>
    route.fulfill({ contentType: 'text/javascript', body: 'throw new Error("broken build")' }))
  await page.goto('bands/1/')

  await expect(page.getByRole('heading', { name: 'Upcoming Shows' })).toBeVisible()
})

test("the home page's first Shows are on screen before the list's data loads", async ({ page }) => {
  await page.route('**/home-shows.json', () => {})  // never answered
  await page.goto('./')

  await expect(page.getByText('Showing 5 of 5 shows')).toBeVisible()
  await expect(showCards(page)).toHaveCount(5)
  await expect(showCards(page).first()).toBeVisible()
  await expect(showCards(page).first()).toContainText('Neon Harbor')
})

test('a filtered home page never shows the unfiltered first page', async ({ page }) => {
  // Hold the list's own code and data: the built (unfiltered) first page is in the HTML, but must stay hidden
  // until the filters apply.
  let release = () => {}
  const held = new Promise<void>(resolve => { release = resolve })
  for (const url of ['**/_astro/HomeShows*.js', '**/home-shows.json'])
    await page.route(url, async route => { await held; await route.continue() })
  await page.goto('./?region=east_bay')

  await expect(page.locator('[data-home-first-page]')).toHaveCount(1)
  await expect(page.getByLabel('Region')).toBeVisible()
  await expect(headliner(page, 'Tidepool Choir')).toBeHidden()

  release()
  await expect(page.locator('[data-home-first-page]')).toHaveCount(0)
  await expect(showCards(page)).toHaveCount(2)
  await expect(headliner(page, 'Tidepool Choir')).toHaveCount(0)
})

test.describe('without JavaScript', () => {
  test.use({ javaScriptEnabled: false })

  test('the home page lists the first page of Shows, with the edition', async ({ page }) => {
    await page.goto('./')
    await expect(page.getByText('Bay Area & Santa Cruz Concert Events — Sep 25, 2026')).toBeVisible()
    await expect(showCards(page)).toHaveCount(5)
    await expect(showCards(page).first()).toBeVisible()
  })
})

test.describe('Shows whose date has passed since the build', () => {
  // Only the page's inline <head> CSS hides them: every script file is blocked.
  test.beforeEach(async ({ page }) => { await page.route('**/_astro/*.js', route => route.abort()) })

  test('are hidden from the home page', async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-10-04T12:00:00-07:00'))  // the Oct 3 Shows have passed
    await page.goto('./')
    await expect(headliner(page, 'Tidepool Choir')).toBeVisible()  // Oct 4
    await expect(headliner(page, 'Gilman Youth')).toBeHidden()     // Oct 3
    await expect(page.getByText(/Saturday, October 3/i)).toBeHidden()
  })

  test("are hidden from a Venue page, which says so when none are left", async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-10-04T12:00:00-07:00'))
    await page.goto('venues/2/')
    const upcoming = page.getByRole('region', { name: 'Upcoming Shows' })
    await expect(upcoming.locator('a[href*="/shows/"]:visible')).toHaveCount(1)  // Oct 5; Oct 3 hidden

    await page.clock.setFixedTime(new Date('2026-10-06T12:00:00-07:00'))
    await page.reload()
    await expect(page.getByText('No upcoming shows.')).toBeVisible()
    await expect(page.getByRole('region', { name: 'Upcoming Shows' })).toBeHidden()
  })

  test("leave a Band page without an Upcoming Shows section when none are left", async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-10-06T12:00:00-07:00'))
    await page.goto('bands/1/')
    await expect(page.getByRole('heading', { level: 1, name: 'Neon Harbor' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Upcoming Shows' })).toBeHidden()
    await expect(page.getByTestId('similar-bands')).toBeVisible()
  })
})

test("the database export isn't published with the site", async ({ page }) => {
  for (const name of ['shows', 'venues', 'bands', 'meta']) {
    expect((await page.request.get(`data/${name}.json`)).status()).toBe(404)
  }
  expect((await page.request.get('home-shows.json')).ok()).toBe(true)
})

test("a Show row's calendar links: a static .ics file and a Google Calendar event", async ({ page }) => {
  await page.goto('./')
  const row = page.locator('[data-recommended]').first()  // Neon Harbor at The Fillmore, Oct 3
  const ics = row.getByRole('link', { name: 'Add to calendar (.ics)' })
  await expect(ics).toHaveAttribute('href', '/the_list/calendar/102.ics')
  await expect(ics).toHaveAttribute('download', 'neon-harbor-2026-10-03.ics')

  const file = await page.request.get('calendar/102.ics')
  expect(file.ok()).toBe(true)
  expect(file.headers()['content-type']).toMatch(/^text\/calendar/)
  const text = await file.text()
  expect(text).toMatch(/^BEGIN:VCALENDAR\r\n/)
  expect(text).toContain('SUMMARY:Neon Harbor at The Fillmore')

  const google = new URL((await row.getByRole('link', { name: 'Add to Google Calendar' }).getAttribute('href'))!)
  expect(google.hostname).toBe('calendar.google.com')
  expect(google.searchParams.get('text')).toBe('Neon Harbor at The Fillmore')
})

test('the Show page links the same .ics file', async ({ page }) => {
  await page.goto('shows/102/')
  await expect(page.getByRole('link', { name: 'Add to calendar' })).toHaveAttribute('href', '/the_list/calendar/102.ics')
})

test('a link with an advanced filter opens Advanced filters', async ({ page }) => {
  await page.goto('./?fromDate=2026-10-04')
  await expect(page.getByLabel('From date')).toHaveValue('2026-10-04')
  await expect(showCards(page)).toHaveCount(3)  // Oct 4, 5 and 10
})
