import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import BandModalProvider from '@/components/BandModalProvider'
import BandLink from '@/components/BandLink'
import { hydrateShows } from '@/lib/data'
import type { ExportBand, ExportShow, ExportVenue, SiteData } from '@/lib/types'

vi.mock('next/navigation', () => ({
  usePathname: () => '/shows/1',
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

// ── site data stub ────────────────────────────────────────────────────────────

const venue: ExportVenue = {
  id: 1, name: 'The Fillmore', address: null, city: 'San Francisco', region: 'sf', websiteUrl: null, latitude: null,
  longitude: null, timezone: null, phone: null, googleRating: null, googlePlaceId: null, description: null,
  wikipediaUrl: null, neighborhood: null, venueType: null, nearestTransit: null, instagram: null, imageUrl: null,
  defaultAgeRestriction: null, isSoberSpace: null, isCashOnly: null, membershipRequired: null,
}
const band = (id: number, name: string, similar: number[], extra: Partial<ExportBand> = {}): ExportBand => ({
  id, name, genres: ['punk'], spotifyUrl: null, soundcloudUrl: null, bandcampUrl: null, websiteUrl: null, imageUrl: null,
  isLocal: null, similar, ...extra,
})
const show = (id: number, date: string, bandId: number): ExportShow => ({
  id, date, doorTime: '20:00:00', setTime: null, priceMin: null, priceMax: null, isFree: false, ageRestriction: 'a/a',
  status: 'upcoming', isRecommended: false, willSellOut: false, isPit: false, isDrinkTickets: false, isNoReentry: false,
  notes: null, isMatinee: false, isSoldOut: false, ticketProvider: null, isBenefit: false, benefitCause: null,
  specialEvent: null, venueId: 1, acts: [[bandId, 0]],
})
const bands = [band(10, 'Headliner', [11], { isLocal: true }), band(11, 'Similar One', [10])]
const shows = [show(1, '2026-10-01', 10), show(2, '2026-09-20', 10), show(3, '2026-10-05', 11)]
const DATA: SiteData = {
  shows: hydrateShows(shows, [venue], bands),
  venues: new Map([[1, venue]]),
  bands: new Map(bands.map(b => [b.id, b])),
  meta: { generatedAt: '', emailSubject: null, filterOptions: { regions: [], ages: [], genres: [], dates: [] }, totalUpcoming: 2 },
}
vi.mock('@/lib/data', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/data')>()),
  loadSiteData: () => Promise.resolve(DATA),
}))

// ── browser setup ─────────────────────────────────────────────────────────────

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  }
})

let push: ReturnType<typeof vi.spyOn>, replace: ReturnType<typeof vi.spyOn>, back: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-01T19:00:00Z'))
  window.history.replaceState(null, '', '/shows/1')
  push = vi.spyOn(window.history, 'pushState')
  replace = vi.spyOn(window.history, 'replaceState')
  // Going back returns to the Show page, whose history entry has no modal state.
  back = vi.spyOn(window.history, 'back').mockImplementation(() => {
    window.dispatchEvent(new PopStateEvent('popstate', { state: null }))
  })
})
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); vi.unstubAllEnvs() })

function renderPage() {
  return render(
    <BandModalProvider>
      <p>Show page</p>
      <BandLink bandId={10}>Headliner</BandLink>
    </BandModalProvider>,
  )
}
const dialog = () => screen.queryByRole('dialog')

describe('BandModalProvider', () => {
  it('opens the Band in a modal and pushes its URL on click', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('link', { name: 'Headliner' }))
    expect(push).toHaveBeenCalledWith(expect.objectContaining({ bandModal: 10 }), '', '/bands/10/')
    const modal = await screen.findByRole('dialog')
    expect(await within(modal).findByRole('heading', { name: 'Headliner' })).toBeInTheDocument()
    expect(screen.getByText('Show page')).toBeInTheDocument()  // page stays underneath
  })

  it('shows the Band details: Local tag, upcoming shows from today, Similar Bands', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('link', { name: 'Headliner' }))
    const modal = await screen.findByRole('dialog')
    await within(modal).findByRole('heading', { name: 'Headliner' })
    expect(within(modal).getByText('Local')).toBeInTheDocument()
    expect(within(modal).getAllByRole('link', { name: /The Fillmore/ })).toHaveLength(1)  // Sep 20 hidden
    expect(within(modal).getByRole('link', { name: /Similar One/ })).toBeInTheDocument()
  })

  it('puts the base path on the Band URL', async () => {
    vi.stubEnv('NEXT_PUBLIC_BASE_PATH', '/the_list')
    renderPage()
    fireEvent.click(screen.getByRole('link', { name: 'Headliner' }))
    expect(push).toHaveBeenCalledWith(expect.objectContaining({ bandModal: 10 }), '', '/the_list/bands/10/')
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it.each([['metaKey'], ['ctrlKey'], ['shiftKey']])('lets %s-click open the full page normally', key => {
    renderPage()
    const notPrevented = fireEvent.click(screen.getByRole('link', { name: 'Headliner' }), { [key]: true })
    expect(notPrevented).toBe(true)
    expect(push).not.toHaveBeenCalled()
    expect(dialog()).not.toBeInTheDocument()
  })

  it('replaces the history entry when moving between Bands inside the modal', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('link', { name: 'Headliner' }))
    const modal = await screen.findByRole('dialog')
    fireEvent.click(await within(modal).findByRole('link', { name: /Similar One/ }))
    expect(replace).toHaveBeenCalledWith(expect.objectContaining({ bandModal: 11 }), '', '/bands/11/')
    expect(push).toHaveBeenCalledTimes(1)
    expect(await within(modal).findByRole('heading', { name: 'Similar One' })).toBeInTheDocument()
  })

  it('closing goes back in history, which closes the modal', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('link', { name: 'Headliner' }))
    const modal = await screen.findByRole('dialog')
    await within(modal).findByRole('heading', { name: 'Headliner' })
    fireEvent.click(within(modal).getByRole('button', { name: 'Close' }))
    expect(back).toHaveBeenCalledTimes(1)
    expect(dialog()).not.toBeInTheDocument()
  })

  it('browser Back closes the modal and Forward reopens it', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('link', { name: 'Headliner' }))
    await screen.findByRole('dialog')
    act(() => { window.dispatchEvent(new PopStateEvent('popstate', { state: null })) })
    expect(dialog()).not.toBeInTheDocument()
    act(() => { window.dispatchEvent(new PopStateEvent('popstate', { state: { bandModal: 10 } })) })
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('BandLink is a plain link without the provider', () => {
    render(<BandLink bandId={10}>Headliner</BandLink>)
    expect(screen.getByRole('link', { name: 'Headliner' })).toHaveAttribute('href', '/bands/10')
  })
})
