import { render, screen, within, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest'
import { http, HttpResponse, type JsonBodyType } from 'msw'
import { setupServer } from 'msw/node'
import HomeShows from '@/components/HomeShows'
import { resetSiteData } from '@/lib/data'
import type { ExportBand, ExportShow, ExportVenue, ExportMeta } from '@/lib/types'

let currentParams = new URLSearchParams()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => currentParams,
  usePathname: () => '/',
}))

// ── fixture JSON (the export's shape) ─────────────────────────────────────────

const TODAY = '2026-10-01'
const venue = (id: number, name: string, neighborhood: string | null = null): ExportVenue => ({
  id, name, address: null, city: 'San Francisco', region: 'sf', websiteUrl: null, latitude: null, longitude: null,
  timezone: null, phone: null, googleRating: null, googlePlaceId: null, description: null, wikipediaUrl: null,
  neighborhood, venueType: null, nearestTransit: null, instagram: null, imageUrl: null, defaultAgeRestriction: null,
  isSoberSpace: null, isCashOnly: null, membershipRequired: null,
})
const band = (id: number, name: string): ExportBand => ({
  id, name, genres: [], spotifyUrl: null, soundcloudUrl: null, bandcampUrl: null, websiteUrl: null, imageUrl: null,
  isLocal: null, similar: [],
})
const show = (id: number, date: string, bandId: number, extra: Partial<ExportShow> = {}): ExportShow => ({
  id, date, doorTime: '20:00:00', setTime: null, priceMin: 15, priceMax: 15, isFree: false, ageRestriction: 'a/a',
  status: 'upcoming', isRecommended: false, willSellOut: false, isPit: false, isDrinkTickets: false,
  isNoReentry: false, notes: null, isMatinee: false, isSoldOut: false, ticketProvider: null, isBenefit: false,
  benefitCause: null, specialEvent: null, venueId: 1, acts: [[bandId, 0]], ...extra,
})

const META: ExportMeta = {
  generatedAt: '2026-10-01T03:00:00Z',
  emailSubject: 'Bay Area & Santa Cruz Concert Events — Sep 25, 2026',
  filterOptions: { regions: ['sf'], ages: ['a/a'], genres: [], dates: [TODAY] },
  totalUpcoming: 3,
}

let files: Record<string, JsonBodyType>
let requested: string[]
const server = setupServer(
  http.get('*/data/:name', ({ params, request }) => {
    requested.push(new URL(request.url).pathname)
    const name = String(params.name).replace(/\.json$/, '')
    return name in files ? HttpResponse.json(files[name]) : new HttpResponse(null, { status: 404 })
  }),
)

beforeAll(() => server.listen())
afterAll(() => server.close())
afterEach(() => { server.resetHandlers(); vi.unstubAllEnvs() })
beforeEach(() => {
  currentParams = new URLSearchParams()
  requested = []
  resetSiteData()
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
  it('shows the email subject from meta', async () => {
    render(<HomeShows />)
    expect(await screen.findByText(/Sep 25, 2026/)).toBeInTheDocument()
  })

  it('lists Upcoming Shows from today (Bay Area time), without past or cancelled ones', async () => {
    render(<HomeShows />)
    await screen.findByText('Tonight Band')
    expect(screen.getByText('Next Week Band')).toBeInTheDocument()
    expect(screen.queryByText('Yesterday Band')).not.toBeInTheDocument()
    expect(screen.queryByText('Cancelled Band')).not.toBeInTheDocument()
  })

  it("lists Steve's Picks under their own date", async () => {
    render(<HomeShows />)
    const card = (await screen.findByText('Pick Band')).closest('a')!
    expect(card).toHaveAttribute('data-recommended')
    expect(within(screen.getByText(/october 2/i).parentElement!).getByText('Pick Band')).toBeInTheDocument()
    expect(screen.getByText('Tonight Band').compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows sold out, benefit and matinee badges, and the venue neighborhood', async () => {
    render(<HomeShows />)
    const card = (await screen.findByText('Tonight Band')).closest('a')!
    expect(within(card).getByText('Sold out')).toBeInTheDocument()
    expect(within(card).getByText('Benefit')).toBeInTheDocument()
    expect(within(card).getByText('Matinee')).toBeInTheDocument()
    expect(within(card).getByText(/Western Addition/)).toBeInTheDocument()
  })

  it('reports how many Shows are listed', async () => {
    render(<HomeShows />)
    expect(await screen.findByText('Showing 3 of 3 shows')).toBeInTheDocument()
  })

  it('loads the data files from under the base path', async () => {
    vi.stubEnv('NEXT_PUBLIC_BASE_PATH', '/the_list')
    render(<HomeShows />)
    await screen.findByText('Tonight Band')
    expect(requested.sort()).toEqual(['/the_list/data/bands.json', '/the_list/data/meta.json',
                                      '/the_list/data/shows.json', '/the_list/data/venues.json'])
  })

  it('shows an error when the data files are missing', async () => {
    files = {}
    render(<HomeShows />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t load/i)
  })

  it('reveals more Shows as the list scrolls', async () => {
    const observers: IntersectionObserverCallback[] = []
    vi.stubGlobal('IntersectionObserver', class {
      constructor(cb: IntersectionObserverCallback) { observers.push(cb) }
      observe() {} disconnect() {} unobserve() {}
    })
    files.bands = Array.from({ length: 60 }, (_, i) => band(100 + i, `Band ${i}`))
    files.shows = Array.from({ length: 60 }, (_, i) => show(100 + i, TODAY, 100 + i, { doorTime: `${String(10 + Math.floor(i / 6)).padStart(2, '0')}:${String((i % 6) * 10).padStart(2, '0')}:00` }))

    render(<HomeShows />)
    await screen.findByText('Band 0')
    expect(screen.queryByText('Band 59')).not.toBeInTheDocument()

    act(() => observers.at(-1)!([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver))
    expect(await screen.findByText('Band 59')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  describe('filters from the URL', () => {
    beforeEach(() => {
      files.venues = [venue(1, 'The Fillmore', 'Western Addition'), { ...venue(2, 'Fox Theater'), region: 'east_bay' }]
      files.bands = [
        { ...band(20, 'Punk Band'), genres: ['punk'] },
        { ...band(21, 'Jazz Band'), genres: ['jazz'] },
        { ...band(22, 'Mystery Band'), genres: [] },
      ]
      files.shows = [
        show(20, TODAY, 20, { priceMin: 10, priceMax: 10 }),
        show(21, '2026-10-02', 21, { venueId: 2, priceMin: 40, priceMax: 40 }),
        show(22, '2026-10-03', 22, { isFree: true, priceMin: 0, priceMax: 0 }),
      ]
      files.meta = { ...META, totalUpcoming: 3 }
    })

    it('filters the list and the count', async () => {
      currentParams = new URLSearchParams('genre=punk')
      render(<HomeShows />)
      expect(await screen.findByText('Punk Band')).toBeInTheDocument()
      expect(screen.queryByText('Jazz Band')).not.toBeInTheDocument()
      expect(screen.queryByText('Mystery Band')).not.toBeInTheDocument()
      expect(screen.getByText('Showing 1 of 3 shows')).toBeInTheDocument()
    })

    it('updates when the URL filters change', async () => {
      const { rerender } = render(<HomeShows />)
      await screen.findByText('Jazz Band')
      expect(screen.getByText('Showing 3 of 3 shows')).toBeInTheDocument()

      currentParams = new URLSearchParams('region=east_bay')
      rerender(<HomeShows />)
      expect(await screen.findByText('Showing 1 of 3 shows')).toBeInTheDocument()
      expect(screen.getByText('Jazz Band')).toBeInTheDocument()
      expect(screen.queryByText('Punk Band')).not.toBeInTheDocument()

      currentParams = new URLSearchParams('free=1')
      rerender(<HomeShows />)
      expect(await screen.findByText('Mystery Band')).toBeInTheDocument()
      expect(screen.queryByText('Jazz Band')).not.toBeInTheDocument()
    })

    it('shows the empty state when nothing matches', async () => {
      currentParams = new URLSearchParams('band=nobody')
      render(<HomeShows />)
      expect(await screen.findByText('No shows match your filters.')).toBeInTheDocument()
    })
  })
})
