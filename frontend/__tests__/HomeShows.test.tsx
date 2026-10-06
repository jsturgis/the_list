import { render, screen, within, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest'
import { http, HttpResponse, type JsonBodyType } from 'msw'
import { setupServer } from 'msw/node'
import HomeShows from '@/components/HomeShows'
import { PAGE_SIZE } from '@/components/ShowList'
import { homePage, homeShows, hydrateShows, resetHomeShows } from '@/lib/data'
import { replaceQuery } from '@/lib/navigation'
import type { ExportBand, ExportShow, ExportVenue, ExportMeta } from '@/lib/types'


// ── fixture JSON (the export's shape) ─────────────────────────────────────────

const TODAY = '2026-10-01'
const venue = (id: number, name: string, neighborhood: string | null = null): ExportVenue => ({
  id, name, address: null, city: 'San Francisco', region: 'sf', websiteUrl: null, latitude: null, longitude: null,
  timezone: null, phone: null, googleRating: null, googlePlaceId: null, description: null, wikipediaUrl: null,
  neighborhood, venueType: null, nearestTransit: null, instagram: null, imageUrl: null, defaultAgeRestriction: null,
  isSoberSpace: null, isCashOnly: null, membershipRequired: null,
})
const band = (id: number, name: string): ExportBand => ({
  id, name, genres: [], spotifyUrl: null, soundcloudUrl: null, bandcampUrl: null, links: [], imageCredit: null, websiteUrl: null, imageUrl: null,
  isLocal: null, description: null, similar: [],
})
const show = (id: number, date: string, bandId: number, extra: Partial<ExportShow> = {}): ExportShow => ({
  id, date, doorTime: '20:00:00', setTime: null, priceMin: 15, priceMax: 15, isFree: false, ageRestriction: 'a/a',
  status: 'upcoming', isRecommended: false, willSellOut: false, isPit: false, isDrinkTickets: false,
  isNoReentry: false, notes: null, isMatinee: false, isSoldOut: false, ticketProvider: null, ticketUrl: null, isBenefit: false,
  benefitCause: null, specialEvent: null, venueId: 1, acts: [[bandId, 0]], ...extra,
})

const META: ExportMeta = {
  generatedAt: '2026-10-01T03:00:00Z',
  emailSubject: 'Bay Area & Santa Cruz Concert Events — Sep 25, 2026',
  filterOptions: { regions: ['sf'], ages: ['a/a'], genres: [], dates: [TODAY] },
  totalUpcoming: 3,
}

// The export, from which the tests build the home page and home-shows.json as the site's build does.
let files: { shows: ExportShow[]; venues: ExportVenue[]; bands: ExportBand[]; meta: ExportMeta } | null
let requested: string[]
let respond: (() => Promise<void>) | null  // set to hold the home-shows.json response
const built = () => hydrateShows(files!.shows, files!.venues, files!.bands)
const page = () => homePage(files ? built() : [], files?.meta ?? META, PAGE_SIZE)
const server = setupServer(
  http.get('*/home-shows.json', async ({ request }) => {
    requested.push(new URL(request.url).pathname)
    await respond?.()
    return files ? HttpResponse.json(homeShows(built(), files.meta) as unknown as JsonBodyType) : new HttpResponse(null, { status: 404 })
  }),
)
const renderHome = () => render(<HomeShows page={page()} />)

beforeAll(() => server.listen())
afterAll(() => server.close())
afterEach(() => { server.resetHandlers(); vi.unstubAllEnvs() })
beforeEach(() => {
  requested = []
  respond = null
  resetHomeShows()
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-01T19:00:00Z'))  // noon Pacific, Oct 1
  files = {
    venues: [venue(1, 'The Fillmore', 'Western Addition')],
    bands: [band(10, 'Yesterday Band'), band(11, 'Tonight Band'), band(12, 'Pick Band'), band(13, 'Cancelled Band'), band(14, 'Next Week Band')],
    shows: [
      show(1, '2026-09-30', 10),
      show(2, TODAY, 11, { isSoldOut: true, isBenefit: true, benefitCause: 'food drive', isMatinee: true }),
      show(3, '2026-10-02', 12, { isRecommended: true }),
      show(4, '2026-10-03', 13, { status: 'cancelled' }),
      show(5, '2026-10-08', 14),
    ],
    meta: META,
  }
})
afterEach(() => vi.useRealTimers())

describe('HomeShows', () => {
  it('lists Upcoming Shows from today (Bay Area time), without past or cancelled ones', async () => {
    renderHome()
    await screen.findByText('Tonight Band')
    expect(screen.getByText('Next Week Band')).toBeInTheDocument()
    expect(screen.queryByText('Yesterday Band')).not.toBeInTheDocument()
    expect(screen.queryByText('Cancelled Band')).not.toBeInTheDocument()
  })

  it("lists Steve's Picks under their own date", async () => {
    renderHome()
    const card = (await screen.findByText('Pick Band')).closest('[data-recommended]')!
    expect(card).not.toBeNull()
    expect(within(screen.getByText(/october 2/i).parentElement!).getByText('Pick Band')).toBeInTheDocument()
    expect(screen.getByText('Tonight Band').compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows sold out, benefit and matinee badges, and the Venue and city without the neighborhood', async () => {
    renderHome()
    const row = (await screen.findByText('Tonight Band')).closest('li')!  // the Show's list item
    expect(within(row).getByText('Sold out')).toBeInTheDocument()
    expect(within(row).getByText('Benefit')).toBeInTheDocument()
    expect(within(row).getByText('Matinee')).toBeInTheDocument()
    expect(within(row).getByText('The Fillmore · San Francisco')).toBeInTheDocument()
    expect(within(row).queryByText(/Western Addition/)).not.toBeInTheDocument()
  })

  it('reports how many Shows are listed', async () => {
    renderHome()
    expect(await screen.findByText('Showing 3 of 3 shows')).toBeInTheDocument()
  })

  describe('before every Show has loaded', () => {
    beforeEach(() => { respond = () => new Promise(() => {}) })  // home-shows.json never arrives

    it("lists the build's first page, without dates that have passed since", () => {
      renderHome()
      expect(screen.getByText('Tonight Band')).toBeInTheDocument()
      expect(screen.getByText('Next Week Band')).toBeInTheDocument()
      expect(screen.queryByText('Yesterday Band')).not.toBeInTheDocument()  // Sep 30: in the build, passed since
      expect(screen.getByText('Showing 3 of 3 shows')).toBeInTheDocument()
    })

    it('marks the first page, so the page can hold it back while the URL has a query', () => {
      const { container } = renderHome()
      expect(container.querySelector('[data-home-first-page]')).not.toBeNull()
      expect(container.querySelector('[data-show-date="2026-10-01"]')).not.toBeNull()
    })

    it('waits for every Show when the URL has filters, as the first page is unfiltered', () => {
      replaceQuery('genre=punk')
      renderHome()
      expect(screen.getByText('Loading…')).toBeInTheDocument()
      expect(screen.getByText('Loading 3 shows…')).toBeInTheDocument()
      expect(screen.queryByText('Tonight Band')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Genre')).toHaveValue('punk')
    })
  })

  it('drops the first-page marks once every Show has loaded', async () => {
    const { container } = renderHome()
    await waitFor(() => expect(container.querySelector('[data-home-first-page]')).toBeNull())
    expect(screen.getByText('Tonight Band')).toBeInTheDocument()
  })

  it('loads home-shows.json from under the base path', async () => {
    vi.stubEnv('BASE_URL', '/the_list/')
    renderHome()
    await screen.findByText('Tonight Band')
    expect(requested).toEqual(['/the_list/home-shows.json'])
  })

  it('shows an error when the data files are missing', async () => {
    files = null
    renderHome()
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t load/i)
  })

  it('reveals more Shows as the list scrolls', async () => {
    const observers: IntersectionObserverCallback[] = []
    vi.stubGlobal('IntersectionObserver', class {
      constructor(cb: IntersectionObserverCallback) { observers.push(cb) }
      observe() {} disconnect() {} unobserve() {}
    })
    files!.bands = Array.from({ length: 60 }, (_, i) => band(100 + i, `Band ${i}`))
    files!.shows = Array.from({ length: 60 }, (_, i) => show(100 + i, TODAY, 100 + i, { doorTime: `${String(10 + Math.floor(i / 6)).padStart(2, '0')}:${String((i % 6) * 10).padStart(2, '0')}:00` }))

    renderHome()
    await screen.findByText('Band 0')
    await waitFor(() => expect(observers).not.toHaveLength(0))  // once every Show has loaded
    expect(screen.queryByText('Band 59')).not.toBeInTheDocument()

    act(() => observers.at(-1)!([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver))
    expect(await screen.findByText('Band 59')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  describe('filters from the URL', () => {
    beforeEach(() => {
      files!.venues = [venue(1, 'The Fillmore', 'Western Addition'), { ...venue(2, 'Fox Theater'), region: 'east_bay' }]
      files!.bands = [
        { ...band(20, 'Punk Band'), genres: ['punk'] },
        { ...band(21, 'Jazz Band'), genres: ['jazz'] },
        { ...band(22, 'Mystery Band'), genres: [] },
      ]
      files!.shows = [
        show(20, TODAY, 20, { priceMin: 10, priceMax: 10 }),
        show(21, '2026-10-02', 21, { venueId: 2, priceMin: 40, priceMax: 40 }),
        show(22, '2026-10-03', 22, { isFree: true, priceMin: 0, priceMax: 0 }),
      ]
      files!.meta = { ...META, totalUpcoming: 3 }
    })

    it('filters the list and the count', async () => {
      replaceQuery('genre=punk')
      renderHome()
      expect(await screen.findByText('Punk Band')).toBeInTheDocument()
      expect(screen.queryByText('Jazz Band')).not.toBeInTheDocument()
      expect(screen.queryByText('Mystery Band')).not.toBeInTheDocument()
      expect(screen.getByText('Showing 1 of 3 shows')).toBeInTheDocument()
    })

    it('updates when the URL filters change', async () => {
      renderHome()
      await screen.findByText('Jazz Band')
      expect(screen.getByText('Showing 3 of 3 shows')).toBeInTheDocument()

      act(() => replaceQuery('region=east_bay'))
      expect(await screen.findByText('Showing 1 of 3 shows')).toBeInTheDocument()
      expect(screen.getByText('Jazz Band')).toBeInTheDocument()
      expect(screen.queryByText('Punk Band')).not.toBeInTheDocument()

      act(() => replaceQuery('free=1'))
      expect(await screen.findByText('Mystery Band')).toBeInTheDocument()
      expect(screen.queryByText('Jazz Band')).not.toBeInTheDocument()
    })

    it('shows the empty state when nothing matches', async () => {
      replaceQuery('q=nobody')
      renderHome()
      expect(await screen.findByText('No shows match your filters.')).toBeInTheDocument()
    })
  })
})
