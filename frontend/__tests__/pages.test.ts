// @vitest-environment node
import { experimental_AstroContainer as AstroContainer } from 'astro/container'
import { getContainerRenderer } from '@astrojs/react/container-renderer'
import { loadRenderers } from 'astro:container'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import NotFoundPage from '@/pages/404.astro'
import AlertsPage from '@/pages/alerts/index.astro'
import UnsubscribePage from '@/pages/alerts/unsubscribe.astro'
import ShowPage from '@/pages/shows/[id].astro'
import VenuePage from '@/pages/venues/[id].astro'
import BandPage from '@/pages/bands/[id].astro'
import { makeBand, makeShow, makeVenue } from './fixtures'

let container: AstroContainer

beforeAll(async () => {
  container = await AstroContainer.create({ renderers: await loadRenderers([getContainerRenderer()]) })
  container.addClientRenderer({ name: '@astrojs/react', entrypoint: '@astrojs/react/client.js' })
})
afterEach(() => vi.unstubAllEnvs())

type Page = Parameters<AstroContainer['renderToString']>[0]
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
    expect(html).toMatch(/<a href="\/"[^>]*>See this week(&#39;|&apos;|')s shows<\/a>/)
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

describe('detail pages ship no React', () => {
  const venue = makeVenue({ id: 2, name: '924 Gilman Street' })
  const band = makeBand({ id: 1, name: 'Neon Harbor' })
  const shows = [
    makeShow({ id: 102, date: '2026-10-03', venue, acts: [{ position: 0, band }] }),
    makeShow({ id: 105, date: '2026-10-05', venue, acts: [{ position: 0, band }] }),
  ]

  it('a Show page has no islands', async () => {
    const html = await render(ShowPage, { show: shows[0] })
    expect(html).toContain('Neon Harbor')
    expect(islands(html)).toEqual([])
  })

  it('marks the page as running JavaScript before it renders, so lists can wait to be trimmed', async () => {
    const html = await render(ShowPage, { show: shows[0] })
    expect(html).toMatch(/<head>.*<script>.*document\.documentElement\.dataset\.js = ''.*<\/script>.*<\/head>/s)
  })

  it('a Venue page lists its Upcoming Shows statically, marked by date for the browser to trim', async () => {
    const html = await render(VenuePage, { venue, upcomingShows: shows })
    expect(islands(html)).toEqual([])
    expect(html).toContain('data-upcoming-shows')
    expect(html).toContain('data-show-date="2026-10-03"')
    expect(html).toContain('data-show-date="2026-10-05"')
  })

  it('a Band page lists its Upcoming Shows statically, marked by date for the browser to trim', async () => {
    const html = await render(BandPage, { band, upcomingShows: shows, similarBands: [] })
    expect(islands(html)).toEqual([])
    expect(html).toContain('data-upcoming-shows')
    expect(html).toContain('data-show-date="2026-10-03"')
  })
})
