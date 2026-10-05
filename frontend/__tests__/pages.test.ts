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

describe('detail pages ship React only for their Upcoming Shows', () => {
  const venue = makeVenue({ id: 2, name: '924 Gilman Street', description: 'A volunteer-run all-ages club.' })
  const band = makeBand({ id: 1, name: 'Neon Harbor', description: 'Synth-pop from Oakland.' })
  const similar = makeBand({ id: 3, name: 'Static Bloom' })
  const shows = [
    makeShow({ id: 102, date: '2026-10-03', venue, acts: [{ position: 0, band }] }),
    makeShow({ id: 105, date: '2026-10-05', venue, acts: [{ position: 0, band }] }),
  ]

  it('a Show page has no islands', async () => {
    const html = await render(ShowPage, { show: shows[0] })
    expect(html).toContain('Neon Harbor')
    expect(islands(html)).toEqual([])
  })

  it("a Venue page hydrates only its Upcoming Shows, given only the Shows", async () => {
    const html = await render(VenuePage, { venue, upcomingShows: shows })
    expect(html).toContain('A volunteer-run all-ages club.')
    const found = islands(html)
    expect(found.map(i => i.component)).toEqual(['VenueShowRows'])
    expect(found[0].props).toContain('&quot;shows&quot;')
    expect(found[0].props).not.toContain('A volunteer-run all-ages club.')
  })

  it('a Band page hydrates only its Upcoming Shows, given only the Shows', async () => {
    const html = await render(BandPage, { band, upcomingShows: shows, similarBands: [similar] })
    expect(html).toContain('Synth-pop from Oakland.')
    expect(html).toContain('Static Bloom')
    const found = islands(html)
    expect(found.map(i => i.component)).toEqual(['BandShows'])
    expect(found[0].props).not.toContain('Static Bloom')
    expect(found[0].props).not.toContain('Synth-pop from Oakland.')
  })
})
