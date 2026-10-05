import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import ShowList from '@/components/ShowList'
import { replaceQuery } from '@/lib/navigation'
import { makeBand, makeShow, makeShowFixtures } from './fixtures'

// ── helpers ───────────────────────────────────────────────────────────────────

const FILTER_OPTIONS = {
  regions: ['east_bay', 'north_bay', 'sf', 'santa_cruz', 'south_bay'],
  ages: ['a/a', '18+', '21+'],
  genres: ['blues', 'folk', 'metal', 'punk', 'rock'],
  dates: ['2026-10-03', '2026-10-04', '2026-10-05'],
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe('ShowList', () => {
  const shows = makeShowFixtures()

  describe('initial render', () => {
    it('renders all passed shows with no filters', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      // Shows count in FilterBar
      expect(screen.getByText(`Showing ${shows.length} of ${shows.length} shows`)).toBeInTheDocument()
    })

    it('has no separate Steve\'s Picks section', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      // A Pick's own row is named "Steve's pick: …"; there's no section heading for Picks.
      expect(screen.queryByRole('heading', { name: /^steve'?s picks?$/i })).not.toBeInTheDocument()
    })

    it('lists a pick under its own date, ahead of that date\'s other shows', () => {
      const dated = [
        makeShow({ id: 1, date: '2026-10-03', acts: [{ position: 0, band: makeBand({ id: 1, name: 'Early Band' }) }] }),
        makeShow({ id: 2, date: '2026-10-04', acts: [{ position: 0, band: makeBand({ id: 2, name: 'Regular Band' }) }] }),
        makeShow({ id: 3, date: '2026-10-04', isRecommended: true, acts: [{ position: 0, band: makeBand({ id: 3, name: 'Pick Band' }) }] }),
      ]
      render(<ShowList shows={dated} dbTotal={3} filterOptions={FILTER_OPTIONS} />)
      const oct3 = screen.getByText(/october 3/i).parentElement!
      const oct4 = screen.getByText(/october 4/i).parentElement!
      expect(within(oct3).queryByText('Pick Band')).not.toBeInTheDocument()
      const headliners = within(oct4).getAllByRole('heading', { level: 3 })  // the date heading is level 2
      expect(headliners.map(h => h.textContent)).toEqual(["Steve's pick: Pick Band", 'Regular Band'])
      expect(headliners[0].closest('[data-recommended]')).not.toBeNull()
    })

    it('groups shows under date headings', () => {
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
      expect(new URLSearchParams(window.location.search).toString()).toContain('region=east_bay')
    })

    it('updates URL when a genre is typed', async () => {
      const user = userEvent.setup()
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await user.type(screen.getByLabelText(/genre/i), 'folk')
      expect(new URLSearchParams(window.location.search).toString()).toContain('genre=folk')
    })

    it('updates URL when free-only is checked', async () => {
      const user = userEvent.setup()
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      await user.click(screen.getByLabelText(/free only/i))
      expect(new URLSearchParams(window.location.search).toString()).toContain('free=1')
    })
  })

  describe('Clear filters button', () => {
    it('shows Clear filters button when filters are active', () => {
      replaceQuery('region=sf')
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      expect(screen.getByRole('button', { name: /clear/i })).toBeInTheDocument()
    })

    it('hides Clear filters button when no filters active', () => {
      render(<ShowList shows={shows} dbTotal={shows.length} filterOptions={FILTER_OPTIONS} />)
      expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument()
    })
  })

})
