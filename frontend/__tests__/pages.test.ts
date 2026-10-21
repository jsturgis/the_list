// @vitest-environment node
import { experimental_AstroContainer as AstroContainer } from 'astro/container'
import { getContainerRenderer } from '@astrojs/react/container-renderer'
import { loadRenderers } from 'astro:container'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import HomePage from '@/pages/index.astro'
import NotFoundPage from '@/pages/404.astro'
import AlertsPage from '@/pages/alerts/index.astro'
import UnsubscribePage from '@/pages/alerts/unsubscribe.astro'
import ShowRoute, { getStaticPaths as showPaths } from '@/pages/shows/[slug].astro'
import VenueRoute, { getStaticPaths as venuePaths } from '@/pages/venues/[slug].astro'
import BandRoute, { getStaticPaths as bandPaths } from '@/pages/bands/[slug].astro'

let container: AstroContainer

beforeAll(async () => {
  container = await AstroContainer.create({ renderers: await loadRenderers([getContainerRenderer()]) })
  container.addClientRenderer({ name: '@astrojs/react', entrypoint: '@astrojs/react/client.js' })
})
afterEach(() => vi.unstubAllEnvs())

type Page = Parameters<AstroContainer['renderToString']>[0]
// A page that can redirect (from its numeric URL) has a return type the container's typing doesn't allow for.
const BandPage = BandRoute as unknown as Page
const VenuePage = VenueRoute as unknown as Page
const ShowPage = ShowRoute as unknown as Page
const render = (page: Page, props: Record<string, unknown> = {}) => container.renderToString(page, { props })

/** The React islands on a rendered page: the component each one loads, and its serialised props. */
function islands(html: string): { component: string; props: string }[] {
  return [...html.matchAll(/<astro-island\b[^>]*>/g)].map(([tag]) => ({
    component: tag.match(/ opts="\{&quot;name&quot;:&quot;([^&]+)&quot;/)?.[1] ?? '',
    props: tag.match(/ props="([^"]*)"/)?.[1] ?? '',
  }))
}

describe('the 404 page', () => {
  it('says the page is missing and links to the Shows list', async () => {
    const html = await render(NotFoundPage)
    expect(html).toMatch(/<h1[^>]*>Page not found<\/h1>/)
    expect(html).toMatch(/<a href="\/"[^>]*>.*?See this week(&#39;|&apos;|')s shows/s)
    expect(html).toContain('<title>The List — SF Bay Area Music</title>')
  })
})

describe('page metadata', () => {
  it('gives the Alerts page its own title and description, indexable', async () => {
    const html = await render(AlertsPage)
    expect(html).toContain('<title>Your alerts — The List</title>')
    expect(html).toContain('content="Saved searches and the weekly email of matching SF Bay Area shows."')
    expect(html).not.toContain('noindex')
  })

  it('keeps the Unsubscribe page out of search indexes', async () => {
    const html = await render(UnsubscribePage)
    expect(html).toContain('<title>Unsubscribe — The List</title>')
    expect(html).toContain('<meta name="robots" content="noindex">')
  })
})

describe('the header', () => {
  it('links to the Alerts page on builds with the Supabase settings, without an island', async () => {
    vi.stubEnv('PUBLIC_SUPABASE_URL', 'https://example.supabase.co')
    vi.stubEnv('PUBLIC_SUPABASE_ANON_KEY', 'sb_publishable_test')
    const html = await render(NotFoundPage)
    expect(html).toMatch(/<a href="\/alerts\/"[^>]*>.*Your alerts<\/a>/s)
    expect(islands(html)).toEqual([])
  })

  it('has no Alerts link without them', async () => {
    vi.stubEnv('PUBLIC_SUPABASE_URL', '')
    expect(await render(NotFoundPage)).not.toContain('Your alerts')
  })
})

// Built from the e2e fixture export (SITE_DATA_DIR): Neon Harbor and 924 Gilman Street both have Shows on Oct 3 and 5.
describe('detail pages ship no React', () => {
  it('a Show page has no islands', async () => {
    const html = await container.renderToString(ShowPage, { params: { slug: 'neon-harbor-2026-10-03' } })
    expect(html).toContain('Neon Harbor')
    expect(islands(html)).toEqual([])
  })

  it('marks the page as running JavaScript before it renders, so lists can wait to be trimmed', async () => {
    const html = await container.renderToString(ShowPage, { params: { slug: 'neon-harbor-2026-10-03' } })
    expect(html).toMatch(/<head>.*<script>.*document\.documentElement\.dataset\.js = ''.*<\/script>.*<\/head>/s)
  })

  it("hides Shows that have passed with CSS written by an inline <head> script, from the export's day", async () => {
    const html = await container.renderToString(ShowPage, { params: { slug: 'neon-harbor-2026-10-03' } })
    const head = html.match(/<head>(.*)<\/head>/s)![1]
    const script = head.match(/<script>(document\.head\.append\(.*?\}\)\))<\/script>/s)![1]
    // Run it as the browser would, on Oct 4 (the fixture export was made on Sep 30), with just enough document.
    const added: { textContent?: string }[] = []
    const document = { createElement: () => ({}), head: { append: (el: { textContent?: string }) => added.push(el) } }
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-04T19:00:00Z'))
    try { new Function('document', script)(document) } finally { vi.useRealTimers() }
    const css = added[0].textContent!
    expect(css).toContain('[data-show-date="2026-09-30"]')
    expect(css).toContain('[data-show-date="2026-10-03"]')
    expect(css).not.toContain('[data-show-date="2026-10-04"]')
  })

  it('a Venue page lists its Upcoming Shows statically, marked by date for the browser to trim', async () => {
    const html = await container.renderToString(VenuePage, { params: { slug: '924-gilman-street' } })
    // The only island is the alert bell, which carries just the Venue's id and name; the list is plain HTML.
    expect(islands(html).map(i => i.component)).toEqual(['AlertBell'])
    expect(islands(html)[0].props).not.toContain('upcomingShows')
    expect(html).toContain('data-upcoming-shows')
    expect(html).toContain('data-show-date="2026-10-03"')
    expect(html).toContain('data-show-date="2026-10-05"')
  })

  it('a Band page lists its Upcoming Shows statically, marked by date for the browser to trim', async () => {
    const html = await container.renderToString(BandPage, { params: { slug: 'neon-harbor' } })
    expect(islands(html).map(i => i.component)).toEqual(['AlertBell'])
    expect(islands(html)[0].props).not.toContain('upcomingShows')
    expect(html).toContain('data-upcoming-shows-list')
    expect(html).toContain('data-show-date="2026-10-03"')
  })
})

// Built from the e2e fixture export (SITE_DATA_DIR).
describe('page URLs', () => {
  const params = async (paths: () => unknown) =>
    ((await paths()) as { params: Record<string, string> }[]).map(p => Object.values(p.params)[0])

  it('builds each Band page at its slug, and its numeric URL too', async () => {
    const built = await params(bandPaths)
    expect(built).toContain('neon-harbor')
    expect(built).toContain('1')
    expect(built).toContain('redwood-sirens')
    expect(built).toContain('7')
  })

  it("renders a Band's page at its slug", async () => {
    const html = await container.renderToString(BandPage, { params: { slug: 'neon-harbor' } })
    expect(html).toMatch(/<h1[^>]*>Neon Harbor<\/h1>/)
  })

  it("redirects a Band's numeric URL to its slug", async () => {
    const response = await container.renderToResponse(BandPage, { params: { slug: '1' } })
    expect(response.status).toBe(301)
    expect(response.headers.get('location')).toBe('/bands/neon-harbor/')
  })

  it('builds each Venue page at its slug, and its numeric URL too', async () => {
    const built = await params(venuePaths)
    expect(built).toEqual(expect.arrayContaining(['the-fillmore', '1', '924-gilman-street', '2', 'the-catalyst', '3']))
  })

  it("renders a Venue's page at its slug", async () => {
    const html = await container.renderToString(VenuePage, { params: { slug: '924-gilman-street' } })
    expect(html).toMatch(/<h1[^>]*>924 Gilman Street<\/h1>/)
  })

  it("redirects a Venue's numeric URL to its slug", async () => {
    const response = await container.renderToResponse(VenuePage, { params: { slug: '2' } })
    expect(response.status).toBe(301)
    expect(response.headers.get('location')).toBe('/venues/924-gilman-street/')
  })

  it('builds each Show page at its headliner and date, and its numeric URL too', async () => {
    const built = await params(showPaths)
    expect(built).toEqual(expect.arrayContaining(['neon-harbor-2026-10-03', '102', 'gilman-youth-2026-10-03', '103']))
  })

  it("renders a Show's page at its slug", async () => {
    const html = await container.renderToString(ShowPage, { params: { slug: 'neon-harbor-2026-10-03' } })
    expect(html).toMatch(/<h1[^>]*>Neon Harbor<\/h1>/)
  })

  it("redirects a Show's numeric URL to its slug", async () => {
    const response = await container.renderToResponse(ShowPage, { params: { slug: '102' } })
    expect(response.status).toBe(301)
    expect(response.headers.get('location')).toBe('/shows/neon-harbor-2026-10-03/')
  })
})

describe('the home page', () => {
  // Built from the e2e fixture export (SITE_DATA_DIR): five Upcoming Shows from Oct 3, exported Oct 1.
  it('has the edition and the first page of Shows in its HTML', async () => {
    const html = await render(HomePage)
    expect(html).toContain('Bay Area &amp; Santa Cruz Concert Events — Sep 25, 2026 — curated by')
    for (const name of ['Neon Harbor', 'Gilman Youth', 'Tidepool Choir', 'Fog City Ramblers']) expect(html).toContain(name)
    expect(html).toContain('Showing 5 of 5 shows')
    expect(html).toContain('data-home-first-page')
    expect(html).toContain('data-show-date="2026-10-03"')
    // So the build's first page can fall back to a loading message if it's gone stale enough that every one
    // of its Shows has since passed (lib/pastShows), the same way a Venue page's list already does.
    expect(html).toContain('data-upcoming-shows')
    expect(html).toContain('data-upcoming-shows-list')
    expect(html).toContain('data-upcoming-shows-empty')
  })

  it("falls back to a loading message, not a silent gap, if the build's first page has gone stale enough that every Show on it has passed", async () => {
    const html = await render(HomePage)
    const head = html.match(/<head>(.*)<\/head>/s)![1]
    const script = head.match(/<script>(document\.head\.append\(.*?\}\)\))<\/script>/s)![1]
    const added: { textContent?: string }[] = []
    const document = { createElement: () => ({}), head: { append: (el: { textContent?: string }) => added.push(el) } }
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-12T19:00:00Z'))  // after every fixture Show's date (the latest is Oct 10)
    try { new Function('document', script)(document) } finally { vi.useRealTimers() }
    const css = added[0].textContent!
    // Every date on the first page's Shows is covered, so pastShowsStyle hides the whole list (CSS targets
    // data-upcoming-shows-list when none of its data-show-date children survive) and reveals data-upcoming-shows-empty.
    for (const date of ['2026-10-03', '2026-10-04', '2026-10-05', '2026-10-10']) expect(css).toContain(`[data-show-date="${date}"]`)
  })

  it('has the Save search button only on builds with the Supabase settings, so it never appears and then goes', async () => {
    vi.stubEnv('PUBLIC_SUPABASE_URL', '')
    expect(await render(HomePage)).not.toContain('Save search')
    vi.stubEnv('PUBLIC_SUPABASE_URL', 'https://example.supabase.co')
    vi.stubEnv('PUBLIC_SUPABASE_ANON_KEY', 'sb_publishable_test')
    expect(await render(HomePage)).toContain('Save search')
  })

  it('hydrates one island, the Shows list', async () => {
    expect(islands(await render(HomePage)).map(i => i.component)).toEqual(['HomeShows'])
  })

  it('marks the page when the URL has a query, so the unfiltered first page can wait', async () => {
    const html = await render(HomePage)
    expect(html).toMatch(/<head>.*if \(location\.search\.length > 1\) document\.documentElement\.dataset\.query = ''.*<\/head>/s)
  })
})
