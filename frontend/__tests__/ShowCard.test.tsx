import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ShowCard, { type ShowCardLayout } from '@/components/ShowCard'
import { makeShow, makeBand } from './fixtures'

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/',
}))

describe.each<ShowCardLayout>(['card', 'row'])('ShowCard (%s layout)', layout => {
  it('renders headliner name', () => {
    render(<ShowCard layout={layout} show={makeShow()} />)
    expect(screen.getByText('Test Band')).toBeInTheDocument()
  })

  it('renders support acts', () => {
    render(
      <ShowCard
        layout={layout}
        show={makeShow({
          acts: [
            { position: 0, band: makeBand({ id: 1, name: 'Headliner' }) },
            { position: 1, band: makeBand({ id: 2, name: 'Support One' }) },
            { position: 2, band: makeBand({ id: 3, name: 'Support Two' }) },
          ],
        })}
      />,
    )
    expect(screen.getByText('Headliner')).toBeInTheDocument()
    expect(screen.getByText(/Support One/)).toBeInTheDocument()
    expect(screen.getByText(/Support Two/)).toBeInTheDocument()
  })

  it('renders venue name and city', () => {
    render(<ShowCard layout={layout} show={makeShow()} />)
    expect(screen.getByText(/The Fillmore/)).toBeInTheDocument()
    expect(screen.getByText(/San Francisco/)).toBeInTheDocument()
  })

  it('renders door time', () => {
    render(<ShowCard layout={layout} show={makeShow({ doorTime: '19:00:00' })} />)
    expect(screen.getByText(/7:00/i)).toBeInTheDocument()
  })

  it('renders price range', () => {
    render(<ShowCard layout={layout} show={makeShow({ priceMin: 25, priceMax: 30 })} />)
    expect(screen.getByText(/\$25/)).toBeInTheDocument()
  })

  it('renders free for free shows', () => {
    render(<ShowCard layout={layout} show={makeShow({ isFree: true, priceMin: 0, priceMax: 0 })} />)
    expect(screen.getByText(/free/i)).toBeInTheDocument()
  })

  it('renders age restriction', () => {
    render(<ShowCard layout={layout} show={makeShow({ ageRestriction: '21+' })} />)
    expect(screen.getByText(/21\+/)).toBeInTheDocument()
  })

  it('renders All Ages label for a/a', () => {
    render(<ShowCard layout={layout} show={makeShow({ ageRestriction: 'a/a' })} />)
    expect(screen.getByText(/all ages/i)).toBeInTheDocument()
  })

  it('renders Steve\'s Pick indicator for recommended shows', () => {
    const { container } = render(<ShowCard layout={layout} show={makeShow({ isRecommended: true })} />)
    expect(container.querySelector('[data-recommended]')).toBeInTheDocument()
  })

  it('does not render Steve\'s Pick indicator for non-recommended shows', () => {
    const { container } = render(<ShowCard layout={layout} show={makeShow({ isRecommended: false })} />)
    expect(container.querySelector('[data-recommended]')).not.toBeInTheDocument()
  })

  it('renders Will Sell Out flag', () => {
    render(<ShowCard layout={layout} show={makeShow({ willSellOut: true })} />)
    expect(screen.getByText(/sell out/i)).toBeInTheDocument()
  })

  it('renders Pit Warning flag', () => {
    render(<ShowCard layout={layout} show={makeShow({ isPit: true })} />)
    expect(screen.getByText(/pit/i)).toBeInTheDocument()
  })

  it('renders Drink Tickets flag', () => {
    render(<ShowCard layout={layout} show={makeShow({ isDrinkTickets: true })} />)
    expect(screen.getByText(/drink/i)).toBeInTheDocument()
  })

  it('renders No Re-entry flag', () => {
    render(<ShowCard layout={layout} show={makeShow({ isNoReentry: true })} />)
    expect(screen.getByText(/re-entry/i)).toBeInTheDocument()
  })

  it('renders Cancelled status', () => {
    render(<ShowCard layout={layout} show={makeShow({ status: 'cancelled' })} />)
    expect(screen.getByText(/cancelled/i)).toBeInTheDocument()
  })

  it('renders Postponed status', () => {
    render(<ShowCard layout={layout} show={makeShow({ status: 'postponed' })} />)
    expect(screen.getByText(/postponed/i)).toBeInTheDocument()
  })

  it('links to show detail page', () => {
    render(<ShowCard layout={layout} show={makeShow({ id: 42 })} />)
    const link = screen.getByRole('link', { name: /Test Band/i })
    expect(link).toHaveAttribute('href', '/shows/42')
  })
})

describe('ShowCard layouts', () => {
  it('defaults to the card layout', () => {
    const { container } = render(<ShowCard show={makeShow()} />)
    expect(container.querySelector('[data-layout="row"]')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Test Band' })).toBeInTheDocument()
  })

  it('renders a compact row when layout="row"', () => {
    const { container } = render(<ShowCard show={makeShow()} layout="row" />)
    expect(container.querySelector('[data-layout="row"]')).toBeInTheDocument()
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })

  it('hides venue when showVenue is false', () => {
    render(<ShowCard show={makeShow()} layout="row" showVenue={false} />)
    expect(screen.queryByText(/The Fillmore/)).not.toBeInTheDocument()
    expect(screen.getByText('Test Band')).toBeInTheDocument()
  })
})
