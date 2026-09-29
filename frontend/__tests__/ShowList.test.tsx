import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import ShowList from '@/components/ShowList'
import { makeShow, makeShowFixtures } from './fixtures'

// ── navigation mock ───────────────────────────────────────────────────────────

const currentParams = new URLSearchParams()
const mockReplace = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockReplace, replace: mockReplace }),
  useSearchParams: () => currentParams,
  usePathname: () => '/',
}))

// ── graphql client mock ───────────────────────────────────────────────────────

const { mockRequest } = vi.hoisted(() => ({ mockRequest: vi.fn() }))

vi.mock('@/lib/graphql', () => ({
  gqlClient: { request: mockRequest },
}))

// ── helpers ───────────────────────────────────────────────────────────────────

function setParams(params: Record<string, string>) {
  for (const key of Array.from(currentParams.keys())) currentParams.delete(key)
  for (const [k, v] of Object.entries(params)) currentParams.set(k, v)
}

const FILTER_OPTIONS = {
  regions: ['east_bay', 'north_bay', 'sf', 'santa_cruz', 'south_bay'],
  ages: ['a/a', '18+', '21+'],
  genres: ['blues', 'folk', 'metal', 'punk', 'rock'],
  dates: ['2026-10-03', '2026-10-04', '2026-10-05'],
}

beforeEach(() => {
  setParams({})
  mockReplace.mockClear()
  mockRequest.mockReset()
  // Default: filtered fetch returns empty (tests that need results configure it)
  mockRequest.mockResolvedValue({ shows: [] })
})

// ── tests ─────────────────────────────────────────────────────────────────────

describe('ShowList', () => {
  const shows = makeShowFixtures()

  describe('initial render', () => {
    it('renders all passed shows with no filters', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      // Shows count in FilterBar
      expect(screen.getByText(`Showing ${shows.length} of ${shows.length} shows`)).toBeInTheDocument()
    })

    it('does not call gqlClient on first render when no filters are active', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      expect(mockRequest).not.toHaveBeenCalled()
    })

    it('renders Steve\'s Picks section for recommended shows', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      expect(screen.getByRole('heading', { name: /steve'?s pick/i })).toBeInTheDocument()
    })

    it('places recommended shows in the Steve\'s Picks section', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      const section = screen.getByTestId('steves-picks')
      expect(within(section).getByText('Headliner Band')).toBeInTheDocument()
      expect(within(section).getByText('Oakland Blues Band')).toBeInTheDocument()
    })

    it('groups non-pick shows under date headings', () => {
      const twoShows = [
        makeShow({ id: 1, date: '2026-10-03' }),
        makeShow({ id: 2, date: '2026-10-04' }),
      ]
      render(<ShowList shows={twoShows} dbTotal={2} filterOptions={FILTER_OPTIONS} />)
      // formatDateLong produces something like "Saturday, October 3, 2026"
      expect(screen.getByText(/october 3/i)).toBeInTheDocument()
      expect(screen.getByText(/october 4/i)).toBeInTheDocument()
    })

    it('renders empty state when no shows are passed and not loading', () => {
      render(<ShowList shows={[]} dbTotal={0} filterOptions={FILTER_OPTIONS} />)
      expect(screen.getByText(/no shows/i)).toBeInTheDocument()
    })

    it('populates genre select from filterOptions', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      const select = screen.getByLabelText(/genre/i)
      const values = Array.from(select.querySelectorAll('option')).map(o => o.value)
      expect(values[0]).toBe('')  // All Genres default
      expect(values).toContain('blues')
      expect(values).toContain('folk')
      expect(values).toContain('punk')
    })

    it('populates region select from filterOptions', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      const select = screen.getByLabelText(/region/i)
      const values = Array.from(select.querySelectorAll('option')).map(o => o.value)
      expect(values).toContain('east_bay')
      expect(values).toContain('sf')
    })
  })

  describe('filter controls → URL updates', () => {
    it('updates URL when region is selected', async () => {
      const user = userEvent.setup()
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await user.selectOptions(screen.getByLabelText(/region/i), 'east_bay')
      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining('region=east_bay'),
        expect.anything(),
      )
    })

    it('updates URL when genre is selected', async () => {
      const user = userEvent.setup()
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await user.selectOptions(screen.getByLabelText(/genre/i), 'folk')
      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining('genre=folk'),
        expect.anything(),
      )
    })

    it('updates URL when free-only is checked', async () => {
      const user = userEvent.setup()
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await user.click(screen.getByLabelText(/free only/i))
      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining('free=1'),
        expect.anything(),
      )
    })
  })

  describe('Clear filters button', () => {
    it('shows Clear filters button when filters are active', () => {
      setParams({ region: 'sf' })
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      expect(screen.getByRole('button', { name: /clear/i })).toBeInTheDocument()
    })

    it('hides Clear filters button when no filters active', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument()
    })
  })

  describe('backend fetch when filters active', () => {
    it('calls gqlClient.request on first render when filters are already set', async () => {
      setParams({ region: 'east_bay' })
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await waitFor(() => expect(mockRequest).toHaveBeenCalledTimes(1))
      const [, variables] = mockRequest.mock.calls[0]
      expect(variables).toMatchObject({ filters: { region: 'east_bay' } })
    })

    it('passes genre filter to gqlClient.request', async () => {
      setParams({ genre: 'punk' })
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await waitFor(() => expect(mockRequest).toHaveBeenCalled())
      const [, variables] = mockRequest.mock.calls[0]
      expect(variables.filters).toMatchObject({ genre: 'punk' })
    })

    it('passes free filter to gqlClient.request', async () => {
      setParams({ free: '1' })
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await waitFor(() => expect(mockRequest).toHaveBeenCalled())
      const [, variables] = mockRequest.mock.calls[0]
      expect(variables.filters).toMatchObject({ isFree: true })
    })

    it('passes band name filter to gqlClient.request', async () => {
      setParams({ band: 'headliner' })
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await waitFor(() => expect(mockRequest).toHaveBeenCalled())
      const [, variables] = mockRequest.mock.calls[0]
      expect(variables.filters).toMatchObject({ bandName: 'headliner' })
    })

    it('passes venue filter to gqlClient.request', async () => {
      setParams({ venue: 'fillmore' })
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await waitFor(() => expect(mockRequest).toHaveBeenCalled())
      const [, variables] = mockRequest.mock.calls[0]
      expect(variables.filters).toMatchObject({ venueName: 'fillmore' })
    })

    it('passes combined filters to gqlClient.request', async () => {
      setParams({ region: 'sf', free: '1' })
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await waitFor(() => expect(mockRequest).toHaveBeenCalled())
      const [, variables] = mockRequest.mock.calls[0]
      expect(variables.filters).toMatchObject({ region: 'sf', isFree: true })
    })

    it('renders shows returned by the filtered fetch', async () => {
      setParams({ region: 'east_bay' })
      mockRequest.mockResolvedValue({
        shows: [makeShow({ id: 2, acts: [{ position: 0, band: { id: 3, name: 'East Bay Band', genres: ['punk'], spotifyUrl: null, soundcloudUrl: null, bandcampUrl: null } }] })],
      })
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await waitFor(() => expect(screen.getByText('East Bay Band')).toBeInTheDocument())
    })

    it('shows loading state while fetch is in progress', async () => {
      setParams({ region: 'sf' })
      // Never resolves so the loading spinner stays up
      mockRequest.mockReturnValue(new Promise(() => {}))
      render(<ShowList shows={[]} dbTotal={0} filterOptions={FILTER_OPTIONS} />)
      expect(screen.getByText(/loading/i)).toBeInTheDocument()
    })

    it('shows empty state when filtered fetch returns no shows', async () => {
      setParams({ band: 'xyznonexistent' })
      mockRequest.mockResolvedValue({ shows: [] })
      render(<ShowList shows={[]} dbTotal={0} filterOptions={FILTER_OPTIONS} />)
      await waitFor(() => expect(screen.getByText(/no shows/i)).toBeInTheDocument())
    })

    it('uses page size of 50 for the initial filtered fetch', async () => {
      setParams({ genre: 'metal' })
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await waitFor(() => expect(mockRequest).toHaveBeenCalled())
      const [, variables] = mockRequest.mock.calls[0]
      expect(variables.limit).toBe(50)
      expect(variables.offset).toBe(0)
    })
  })
})
