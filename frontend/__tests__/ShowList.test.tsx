import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import ShowList from '@/components/ShowList'
import { makeShowFixtures } from './fixtures'

// Mutable URLSearchParams that the mock reads from
const currentParams = new URLSearchParams()
const mockReplace = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockReplace, replace: mockReplace }),
  useSearchParams: () => currentParams,
  usePathname: () => '/',
}))

function setParams(params: Record<string, string>) {
  for (const key of Array.from(currentParams.keys())) currentParams.delete(key)
  for (const [k, v] of Object.entries(params)) currentParams.set(k, v)
}

beforeEach(() => {
  setParams({})
  mockReplace.mockClear()
})

describe('ShowList', () => {
  const shows = makeShowFixtures()

  it('renders all shows when no filters active', () => {
    render(<ShowList shows={shows} />)
    expect(screen.getByText('20 shows')).toBeInTheDocument()
  })

  it('renders Steve\'s Picks section heading', () => {
    render(<ShowList shows={shows} />)
    expect(screen.getByRole('heading', { name: /steve'?s pick/i })).toBeInTheDocument()
  })

  it('shows recommended shows in the Steve\'s Picks section', () => {
    render(<ShowList shows={shows} />)
    const picksSection = screen.getByTestId('steves-picks')
    expect(within(picksSection).getByText('Headliner Band')).toBeInTheDocument()
    expect(within(picksSection).getByText('Oakland Blues Band')).toBeInTheDocument()
  })

  it('filters by region (East Bay)', () => {
    setParams({ region: 'east_bay' })
    render(<ShowList shows={shows} />)
    // East Bay shows: 2 (Berkeley), 10 (Oakland), 12 (Oakland), 19 (Berkeley)
    expect(screen.getByText(/4 of 20 shows/)).toBeInTheDocument()
    expect(screen.getByText('East Bay Band')).toBeInTheDocument()
    expect(screen.queryByText('North Bay Band')).not.toBeInTheDocument()
  })

  it('filters by maximum price', () => {
    setParams({ priceMax: '15' })
    render(<ShowList shows={shows} />)
    // Shows with priceMin <= 15: free shows + $10, $5, $12, $8, $15 min
    expect(screen.queryByText('Headliner Band')).not.toBeInTheDocument() // $25 min
    expect(screen.getByText('East Bay Band')).toBeInTheDocument()        // free
    expect(screen.getByText('Santa Cruz Band')).toBeInTheDocument()      // $10
  })

  it('filters by free only', () => {
    setParams({ free: '1' })
    render(<ShowList shows={shows} />)
    // Free shows: 2 (Berkeley), 10 (Oakland), 14 (Mountain View), 18 (SF)
    expect(screen.getByText(/4 of 20 shows/)).toBeInTheDocument()
    expect(screen.getByText('East Bay Band')).toBeInTheDocument()
    expect(screen.queryByText('Headliner Band')).not.toBeInTheDocument()
  })

  it('filters by band name (partial, case-insensitive)', () => {
    setParams({ band: 'bay' })
    render(<ShowList shows={shows} />)
    expect(screen.getByText('East Bay Band')).toBeInTheDocument()
    expect(screen.getByText('North Bay Band')).toBeInTheDocument()
    expect(screen.getByText('South Bay Band')).toBeInTheDocument()
    expect(screen.queryByText('Headliner Band')).not.toBeInTheDocument()
  })

  it('filters by age restriction (all ages)', () => {
    setParams({ age: 'a/a' })
    render(<ShowList shows={shows} />)
    // All-ages shows: 2, 5, 9, 10, 14, 15, 20
    expect(screen.getByText('East Bay Band')).toBeInTheDocument()
    expect(screen.queryByText('Headliner Band')).not.toBeInTheDocument() // 21+
  })

  it('combines region + free filters', () => {
    setParams({ region: 'east_bay', free: '1' })
    render(<ShowList shows={shows} />)
    // East Bay + free: shows 2, 10
    expect(screen.getByText(/2 of 20 shows/)).toBeInTheDocument()
    expect(screen.getByText('East Bay Band')).toBeInTheDocument()
    expect(screen.getByText('Oakland Blues Band')).toBeInTheDocument()
    expect(screen.queryByText('Folk Duo')).not.toBeInTheDocument()
  })

  it('shows result count for filtered set', () => {
    setParams({ region: 'santa_cruz' })
    render(<ShowList shows={shows} />)
    // Santa Cruz shows: 5, 17
    expect(screen.getByText(/2 of 20 shows/)).toBeInTheDocument()
  })

  it('renders empty state when no shows match', () => {
    setParams({ band: 'xyznonexistent' })
    render(<ShowList shows={shows} />)
    expect(screen.getByText(/no shows/i)).toBeInTheDocument()
  })

  it('calls router.replace with updated region param', async () => {
    const user = userEvent.setup()
    render(<ShowList shows={shows} />)
    await user.selectOptions(screen.getByLabelText(/region/i), 'east_bay')
    expect(mockReplace).toHaveBeenCalledWith(
      expect.stringContaining('region=east_bay'),
      expect.anything(),
    )
  })

  it('shows Clear filters button when filters are active', () => {
    setParams({ region: 'sf' })
    render(<ShowList shows={shows} />)
    expect(screen.getByRole('button', { name: /clear/i })).toBeInTheDocument()
  })

  it('hides Clear filters button when no filters active', () => {
    render(<ShowList shows={shows} />)
    expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument()
  })

  it('reflects free filter in URL via router.replace', async () => {
    const user = userEvent.setup()
    render(<ShowList shows={shows} />)
    await user.click(screen.getByLabelText(/free only/i))
    expect(mockReplace).toHaveBeenCalledWith(
      expect.stringContaining('free=1'),
      expect.anything(),
    )
  })
})
