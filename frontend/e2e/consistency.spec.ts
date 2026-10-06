import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

// Every page shares one shell (DESIGN.md §5 and §9): the same column, the same page title and the same section
// headings. These compare the rendered pages with each other at desktop width.

const NARROW: [name: string, path: string][] = [
  ['Show page', 'shows/102/'],
  ['Venue page', 'venues/2/'],
  ['Band page', 'bands/1/'],
  ['Alerts page', 'alerts/'],
  ['Unsubscribe page', 'alerts/unsubscribe/'],
  ['not-found page', 'shows/99999/'],
]
const DETAIL = new Set(['Show page', 'Venue page', 'Band page'])

test.use({ viewport: { width: 1280, height: 800 } })

/** The h1's box and type, and the Back link's left edge if there is one. */
async function measure(page: Page) {
  const h1 = page.getByRole('heading', { level: 1 })
  await expect(h1).toBeVisible()
  const box = (await h1.boundingBox())!
  const type = await h1.evaluate(el => {
    const s = getComputedStyle(el)
    return { size: s.fontSize, weight: s.fontWeight }
  })
  const back = page.getByRole('link', { name: 'Back' })
  const backX = (await back.count()) ? (await back.boundingBox())!.x : null
  return { x: Math.round(box.x), width: Math.round(box.width), backX: backX === null ? null : Math.round(backX), ...type }
}

test('narrow pages share one 672px column, with Back aligned to it', async ({ page }) => {
  for (const [name, path] of NARROW) {
    await page.goto(path)
    const m = await measure(page)
    expect({ name, x: m.x, width: m.width }).toEqual({ name, x: 304, width: 672 })  // (1280 − 672) / 2
    if (DETAIL.has(name)) expect({ name, backX: m.backX }).toEqual({ name, backX: 304 })
  }
})

test('every page title has the same size and weight', async ({ page }) => {
  for (const [name, path] of [['home', './'], ...NARROW]) {
    await page.goto(path)
    const { size, weight } = await measure(page)
    expect({ name, size, weight }).toEqual({ name, size: '36px', weight: '800' })
  }
})

test('section headings are the same size on every page', async ({ page }) => {
  const sizes = new Map<string, string[]>()
  for (const [name, path] of NARROW) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    for (const size of await page.locator('main section > h2').evaluateAll(hs => hs.map(h => getComputedStyle(h).fontSize))) {
      sizes.set(size, [...(sizes.get(size) ?? []), name])
    }
  }
  expect([...sizes.keys()], JSON.stringify(Object.fromEntries(sizes))).toEqual(['24px'])
})
