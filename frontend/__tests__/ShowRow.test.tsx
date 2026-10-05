import { render, screen, within } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ShowRow from '@/components/ShowRow'
import { makeShow, makeBand, makeVenue } from './fixtures'

const showLink = () => screen.getByRole('link', { name: /Test Band/ })

describe('ShowRow', () => {
  it('names the headliner in a heading that links to the Show page', () => {
    render(<ShowRow show={makeShow({ id: 42 })} />)
    expect(screen.getByRole('heading', { level: 3, name: /Test Band/ })).toBeInTheDocument()
    expect(showLink()).toHaveAttribute('href', '/shows/42/')
  })

  it('can sit one level deeper, under a Venue page\'s date headings', () => {
    render(<ShowRow show={makeShow()} headingLevel={4} />)
    expect(screen.getByRole('heading', { level: 4, name: /Test Band/ })).toBeInTheDocument()
  })

  it('carries the Shows list filters to the Show page', () => {
    render(<ShowRow show={makeShow({ id: 42 })} filterQs="region=sf" />)
    expect(showLink()).toHaveAttribute('href', '/shows/42/?region=sf')
  })

  it('lists the supports after "with"', () => {
    render(<ShowRow show={makeShow({
      acts: [
        { position: 0, band: makeBand({ id: 1, name: 'Headliner' }) },
        { position: 1, band: makeBand({ id: 2, name: 'Support One' }) },
        { position: 2, band: makeBand({ id: 3, name: 'Support Two' }) },
      ],
    })} />)
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Headliner with Support One, Support Two')
    expect(screen.getByRole('link', { name: 'Headliner' })).toBeInTheDocument()
  })

  it('shows the Venue and city, but not the neighborhood or street address', () => {
    const venue = makeVenue({ name: 'Sweetwater Music Hall', city: 'Mill Valley', neighborhood: '19 Corte Madera Ave', address: '19 Corte Madera Ave, Mill Valley' })
    render(<ShowRow show={makeShow({ venue })} />)
    expect(screen.getByText('Sweetwater Music Hall · Mill Valley')).toBeInTheDocument()
    expect(screen.queryByText(/Corte Madera/)).not.toBeInTheDocument()
  })

  it('leaves the Venue out when showVenue is false', () => {
    render(<ShowRow show={makeShow()} showVenue={false} />)
    expect(screen.queryByText(/The Fillmore/)).not.toBeInTheDocument()
  })

  it('gives door time, price and age on one line', () => {
    render(<ShowRow show={makeShow({ doorTime: '19:00:00', priceMin: 25, priceMax: 30, ageRestriction: '21+' })} />)
    expect(screen.getByText('7:00 PM · $25–$30 · 21+')).toBeInTheDocument()
  })

  it('says Free and All Ages', () => {
    render(<ShowRow show={makeShow({ isFree: true, priceMin: 0, priceMax: 0, ageRestriction: 'a/a' })} />)
    expect(screen.getByText(/Free · All Ages/)).toBeInTheDocument()
  })

  it("marks a Steve's Pick, for screen readers too", () => {
    const { container } = render(<ShowRow show={makeShow({ isRecommended: true })} />)
    expect(container.querySelector('[data-recommended]')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^Steve's pick:\s*Test Band$/ })).toBeInTheDocument()
  })

  it("doesn't mark other Shows as picks", () => {
    const { container } = render(<ShowRow show={makeShow({ isRecommended: false })} />)
    expect(container.querySelector('[data-recommended]')).not.toBeInTheDocument()
    expect(screen.queryByText(/Steve's pick/)).not.toBeInTheDocument()
  })

  it('shows the flags', () => {
    render(<ShowRow show={makeShow({ willSellOut: true, isPit: true, isDrinkTickets: true, isNoReentry: true })} />)
    for (const flag of ['Will Sell Out', 'Pit Warning', 'Drink Tickets', 'No Re-entry']) expect(screen.getByText(flag)).toBeInTheDocument()
  })

  it('marks Cancelled and Postponed Shows', () => {
    const { rerender } = render(<ShowRow show={makeShow({ status: 'cancelled' })} />)
    expect(screen.getByText(/cancelled/i)).toBeInTheDocument()
    rerender(<ShowRow show={makeShow({ status: 'postponed' })} />)
    expect(screen.getByText(/postponed/i)).toBeInTheDocument()
  })

  describe('calendar links', () => {
    it("link an Upcoming Show's .ics file and its Google Calendar event", () => {
      render(<ShowRow show={makeShow({ id: 42, date: '2026-10-03', acts: [{ position: 0, band: makeBand({ name: 'Neon Harbor' }) }] })} />)
      const ics = screen.getByRole('link', { name: 'Add to calendar (.ics)' })
      expect(ics).toHaveAttribute('href', '/calendar/42.ics')
      expect(ics).toHaveAttribute('download', 'neon-harbor-2026-10-03.ics')
      const google = screen.getByRole('link', { name: 'Add to Google Calendar' })
      expect(new URL(google.getAttribute('href')!).hostname).toBe('calendar.google.com')
      expect(google).toHaveAttribute('target', '_blank')
    })

    it('use the street address for the event location', () => {
      const venue = makeVenue({ name: 'The Chapel', city: 'San Francisco', address: '777 Valencia St, San Francisco' })
      render(<ShowRow show={makeShow({ venue })} />)
      const url = new URL(screen.getByRole('link', { name: 'Add to Google Calendar' }).getAttribute('href')!)
      expect(url.searchParams.get('location')).toBe('The Chapel, 777 Valencia St, San Francisco')
    })

    it("aren't offered for Cancelled or Postponed Shows", () => {
      for (const status of ['cancelled', 'postponed']) {
        const { unmount } = render(<ShowRow show={makeShow({ status })} />)
        expect(screen.queryByRole('link', { name: /calendar/i })).not.toBeInTheDocument()
        unmount()
      }
    })

    it('are labelled for phones, where they get their own line', () => {
      render(<ShowRow show={makeShow()} />)
      const ics = screen.getByRole('link', { name: 'Add to calendar (.ics)' })
      expect(within(ics).getByText('.ics')).toBeInTheDocument()
      expect(within(screen.getByRole('link', { name: 'Add to Google Calendar' })).getByText('Google Calendar')).toBeInTheDocument()
    })
  })
})
