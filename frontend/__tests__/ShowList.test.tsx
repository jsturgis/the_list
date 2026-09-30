import { fireEvent, render, screen, within } from '@testing-library/react'
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

    it('populates genre suggestions from filterOptions', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      fireEvent.focus(screen.getByLabelText(/genre/i))
      const values = within(screen.getByRole('listbox')).getAllByRole('option').map(o => o.textContent)
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

    it('updates URL when a genre is typed', async () => {
      const user = userEvent.setup()
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await user.type(screen.getByLabelText(/genre/i), 'folk')
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

})
