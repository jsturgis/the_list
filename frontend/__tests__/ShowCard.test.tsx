import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ShowCard from '@/components/ShowCard'
import { makeShow, makeVenue, makeBand } from './fixtures'

describe('ShowCard', () => {
  it('renders headliner name', () => {
    render(<ShowCard show={makeShow()} />)
    expect(screen.getByText('Test Band')).toBeInTheDocument()
  })

  it('renders support acts', () => {
    render(
      <ShowCard
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
    render(<ShowCard show={makeShow()} />)
    expect(screen.getByText(/The Fillmore/)).toBeInTheDocument()
    expect(screen.getByText(/San Francisco/)).toBeInTheDocument()
  })

  it('renders door time', () => {
    render(<ShowCard show={makeShow({ doorTime: '19:00:00' })} />)
    expect(screen.getByText(/7:00/i)).toBeInTheDocument()
  })

  it('renders price range', () => {
    render(<ShowCard show={makeShow({ priceMin: 25, priceMax: 30 })} />)
    expect(screen.getByText(/\$25/)).toBeInTheDocument()
  })

  it('renders free for free shows', () => {
    render(<ShowCard show={makeShow({ isFree: true, priceMin: 0, priceMax: 0 })} />)
    expect(screen.getByText(/free/i)).toBeInTheDocument()
  })

  it('renders age restriction', () => {
    render(<ShowCard show={makeShow({ ageRestriction: '21+' })} />)
    expect(screen.getByText(/21\+/)).toBeInTheDocument()
  })

  it('renders All Ages label for a/a', () => {
    render(<ShowCard show={makeShow({ ageRestriction: 'a/a' })} />)
    expect(screen.getByText(/all ages/i)).toBeInTheDocument()
  })

  it('renders Steve\'s Pick indicator for recommended shows', () => {
    const { container } = render(<ShowCard show={makeShow({ isRecommended: true })} />)
    expect(container.querySelector('[data-recommended]')).toBeInTheDocument()
  })

  it('does not render Steve\'s Pick indicator for non-recommended shows', () => {
    const { container } = render(<ShowCard show={makeShow({ isRecommended: false })} />)
    expect(container.querySelector('[data-recommended]')).not.toBeInTheDocument()
  })

  it('renders Will Sell Out flag', () => {
    render(<ShowCard show={makeShow({ willSellOut: true })} />)
    expect(screen.getByText(/sell out/i)).toBeInTheDocument()
  })

  it('renders Pit Warning flag', () => {
    render(<ShowCard show={makeShow({ isPit: true })} />)
    expect(screen.getByText(/pit/i)).toBeInTheDocument()
  })

  it('renders Drink Tickets flag', () => {
    render(<ShowCard show={makeShow({ isDrinkTickets: true })} />)
    expect(screen.getByText(/drink/i)).toBeInTheDocument()
  })

  it('renders No Re-entry flag', () => {
    render(<ShowCard show={makeShow({ isNoReentry: true })} />)
    expect(screen.getByText(/re-entry/i)).toBeInTheDocument()
  })

  it('renders Cancelled status', () => {
    render(<ShowCard show={makeShow({ status: 'cancelled' })} />)
    expect(screen.getByText(/cancelled/i)).toBeInTheDocument()
  })

  it('renders Postponed status', () => {
    render(<ShowCard show={makeShow({ status: 'postponed' })} />)
    expect(screen.getByText(/postponed/i)).toBeInTheDocument()
  })

  it('links to show detail page', () => {
    render(<ShowCard show={makeShow({ id: 42 })} />)
    const link = screen.getByRole('link', { name: /Test Band/i })
    expect(link).toHaveAttribute('href', '/shows/42')
  })
})
