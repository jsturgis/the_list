// Screenshots of every page, at desktop and phone width in light and dark mode, for reviewing design changes
// (DESIGN.md). Run on demand,
// not in CI: `npm run screenshots -- <output dir> [built site dir]`.
//
// Without a built site, it builds this tree from the e2e fixtures (as e2e/serve.sh does), with placeholder
// Supabase settings so the Alerts features render (nothing is sent to Supabase). With one (a directory holding
// the_list/), it photographs that instead, e.g. a build of main for "before" shots.
import { spawn, spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { chromium } from '@playwright/test'

const [outArg, siteArg] = process.argv.slice(2)
if (!outArg) {
  console.error('Usage: npm run screenshots -- <output dir> [built site dir]')
  process.exit(1)
}
const out = resolve(outArg)
mkdirSync(out, { recursive: true })

let site = siteArg && resolve(siteArg)
if (!site) {
  site = mkdtempSync(join(tmpdir(), 'the-list-screenshots-'))
  const build = spawnSync('npx', ['astro', 'build', '--outDir', join(site, 'the_list')], {
    stdio: 'inherit',
    env: {
      ...process.env,
      SITE_DATA_DIR: 'e2e/fixtures/data',
      PUBLIC_SUPABASE_URL: 'https://screenshots.invalid',
      PUBLIC_SUPABASE_ANON_KEY: 'sb_publishable_screenshots',
      ASTRO_TELEMETRY_DISABLED: '1',
    },
  })
  if (build.status !== 0) process.exit(build.status ?? 1)
}

const port = 4400 + Math.floor(Math.random() * 500)
const server = spawn('node', ['e2e/server.mjs', site, String(port)], { stdio: 'ignore' })
const base = `http://127.0.0.1:${port}/the_list/`

/** [file name, path, optional step before the screenshot] */
const PAGES = [
  ['home', ''],
  ['show', 'shows/102/'],
  ['venue', 'venues/2/'],
  ['band', 'bands/1/'],
  ['alerts', 'alerts/'],
  ['unsubscribe', 'alerts/unsubscribe/'],
  ['not-found', 'shows/99999/'],
  ['setup-alert-panel', '?region=east_bay', page => page.getByRole('button', { name: /setup alert|save search/i }).click()],
]

try {
  for (let i = 0; i < 50; i++) {
    if (await fetch(base).then(r => r.ok, () => false)) break
    await new Promise(r => setTimeout(r, 100))
  }
  const browser = await chromium.launch()
  const DEVICES = [['desktop', { viewport: { width: 1100, height: 900 } }], ['phone', { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 }]]
  for (const [device, options] of DEVICES) for (const scheme of ['light', 'dark']) {
    const context = await browser.newContext({ ...options, colorScheme: scheme })
    for (const [name, path, step] of PAGES) {
      const page = await context.newPage()
      await page.clock.setFixedTime(new Date('2026-10-01T12:00:00-07:00'))  // the fixtures' "today"
      await page.goto(base + path, { waitUntil: 'networkidle' })
      if (step) await step(page)
      await page.evaluate(() => document.fonts.ready)
      await page.waitForTimeout(300)
      await page.screenshot({ path: join(out, `${name}-${device}-${scheme}.png`), fullPage: true })
      await page.close()
    }
    await context.close()
  }
  await browser.close()
  console.log(`Screenshots in ${out}`)
} finally {
  server.kill()
}
