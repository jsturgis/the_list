import { expect, test } from './fixtures'

// The docs (Starlight, ADR 0005): the Markdown guides in docs/guide/, at /docs/. __tests__/docs.test.ts checks the
// guides as files; these check the built pages.

const GUIDES = ['overview', 'architecture', 'local-setup', 'configuration', 'ingestion', 'deployment', 'alerts', 'project-structure']

test('the docs home page links to every guide, in its text and in the sidebar', async ({ page }) => {
  await page.goto('docs/')
  await expect(page.getByRole('heading', { level: 1, name: 'Docs' })).toBeVisible()
  for (const guide of GUIDES) {
    await expect(page.locator(`main a[href="./${guide}/"]`)).toBeVisible()
    await expect(page.locator(`nav[aria-label="Main"] a[href$="/docs/${guide}/"]`)).toHaveCount(1)
  }
})

test('a guide has its title, a table of contents, an edit link and the next guide', async ({ page }) => {
  await page.goto('docs/local-setup/')
  await expect(page.getByRole('heading', { level: 1, name: 'Local setup' })).toBeVisible()
  await expect(page).toHaveTitle('Local setup | The List')
  await expect(page.getByRole('navigation', { name: 'On this page' }).getByRole('link', { name: 'Database migrations' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Edit page' }))
    .toHaveAttribute('href', 'https://github.com/jsturgis/the_list/edit/main/docs/guide/local-setup.md')
  await page.getByRole('link', { name: /Next\s+Configuration/ }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Configuration' })).toBeVisible()
})

test('the sidebar marks the current guide and leads back to the Shows', async ({ page }) => {
  await page.goto('docs/deployment/')
  const sidebar = page.getByRole('navigation', { name: 'Main' })
  await expect(sidebar.getByRole('link', { name: 'Deployment' })).toHaveAttribute('aria-current', 'page')
  await sidebar.getByRole('link', { name: 'Back to the Shows' }).click()
  await expect(page.locator('main [data-show-link]').first()).toBeVisible()
})

test('every link between guides lands on a page, and on a heading that exists', async ({ page, request }) => {
  const ids = new Map<string, Set<string>>()
  const links: { from: string; path: string; hash: string }[] = []
  for (const guide of ['', ...GUIDES.map(g => `${g}/`)]) {
    await page.goto(`docs/${guide}`)
    ids.set(new URL(page.url()).pathname, new Set(await page.locator('[id]').evaluateAll(els => els.map(el => el.id))))
    for (const href of await page.locator('.sl-markdown-content a').evaluateAll(as => as.map(a => (a as HTMLAnchorElement).href))) {
      const url = new URL(href)
      if (url.origin === new URL(page.url()).origin) links.push({ from: guide || 'index', path: url.pathname, hash: decodeURIComponent(url.hash.slice(1)) })
    }
  }
  expect(links.length).toBeGreaterThan(20)
  for (const { from, path, hash } of links) {
    if (!ids.has(path)) {
      expect((await request.get(path)).status(), `${from} → ${path}`).toBe(200)
    } else if (hash) {
      expect([...ids.get(path)!], `${from} → ${path}#${hash}`).toContain(hash)
    }
  }
})

test('a diagram is drawn from its Mermaid source, in a named region', async ({ page }) => {
  await page.goto('docs/architecture/')
  const diagram = page.getByRole('region', { name: 'Diagram: The site at build time' })
  await expect(diagram.locator('.docs-diagram-svg > svg')).toBeVisible()
  await expect(diagram.locator('pre')).toBeHidden()
  await expect(page.locator('[data-diagram]')).toHaveCount(6)
})

test('search finds a guide by a word in it', async ({ page }) => {
  await page.goto('docs/')
  await page.getByRole('button', { name: 'Search' }).click()
  await page.getByRole('dialog').locator('input').fill('Backfill')
  await expect(page.getByRole('dialog').getByRole('link', { name: /Deployment/ }).first()).toBeVisible()
})

test('the docs follow the system colour scheme, with no switch of their own', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('docs/overview/')
  await expect(page.locator('starlight-theme-select')).toHaveCount(0)
  const dark = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  await page.emulateMedia({ colorScheme: 'light' })
  const light = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  expect(dark).toBe('rgb(18, 18, 18)')    // page, dark
  expect(light).toBe('rgb(246, 246, 246)')  // page, light
})

test("a docs URL that doesn't exist gets the site's own not-found page", async ({ page }) => {
  await page.goto('docs/no-such-guide/')
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
})
