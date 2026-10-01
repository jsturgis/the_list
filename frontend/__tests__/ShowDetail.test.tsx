import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ShowDetail from '@/components/ShowDetail'
import { makeShow, makeVenue, makeBand } from './fixtures'

let currentParams = new URLSearchParams()
vi.mock('next/navigation', () => ({ useSearchParams: () => currentParams }))
beforeEach(() => { currentParams = new URLSearchParams() })

describe('ShowDetail', () => {
  const show = makeShow({
    id: 1,
    date: '2026-10-03',
    doorTime: '19:00:00',
    setTime: '20:00:00',
    venue: makeVenue({
      name: 'The Fillmore',
      address: '1805 Geary Blvd, San Francisco, CA 94115',
      city: 'San Francisco',
      region: 'sf',
      websiteUrl: 'https://www.thefillmore.com',
    }),
    acts: [
      { position: 0, band: makeBand({ id: 1, name: 'Headliner Act', genres: ['rock'] }) },
      { position: 1, band: makeBand({ id: 2, name: 'Support One', genres: ['indie'] }) },
      { position: 2, band: makeBand({ id: 3, name: 'Opener', genres: ['folk'] }) },
    ],
    priceMin: 25,
    priceMax: 30,
    isFree: false,
    ageRestriction: '21+',
    status: 'upcoming',
    isRecommended: false,
    willSellOut: false,
    isPit: false,
    isDrinkTickets: false,
    isNoReentry: false,
    notes: null,
  })

  it('renders all acts in order', () => {
    render(<ShowDetail show={show} />)
    const actNames = screen.getAllByTestId('act-name').map(el => el.textContent)
    expect(actNames).toEqual(['Headliner Act', 'Support One', 'Opener'])
  })

  it('marks the headliner in bold instead of with a label', () => {
    render(<ShowDetail show={show} />)
    expect(screen.queryByText(/^Headliner$/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Headliner Act' })).toHaveClass('font-bold')
    expect(screen.getByRole('link', { name: 'Support One' })).not.toHaveClass('font-bold')
  })

  it('links each act to its band page', () => {
    render(<ShowDetail show={show} />)
    expect(screen.getByRole('link', { name: /Headliner Act/i })).toHaveAttribute('href', '/bands/1')
    expect(screen.getByRole('link', { name: /Support One/i })).toHaveAttribute('href', '/bands/2')
    expect(screen.getByRole('link', { name: /Opener/i })).toHaveAttribute('href', '/bands/3')
  })

  it('renders venue address', () => {
    render(<ShowDetail show={show} />)
    expect(screen.getByText(/1805 Geary Blvd/)).toBeInTheDocument()
  })

  it('renders venue website link', () => {
    render(<ShowDetail show={show} />)
    const link = screen.getByRole('link', { name: /venue website/i })
    expect(link).toHaveAttribute('href', 'https://www.thefillmore.com')
  })

  it('does not render venue website link when websiteUrl is null', () => {
    render(<ShowDetail show={makeShow({ venue: makeVenue({ websiteUrl: null }) })} />)
    expect(screen.queryByRole('link', { name: /venue website/i })).not.toBeInTheDocument()
  })

  it('renders Cancelled status prominently', () => {
    render(<ShowDetail show={makeShow({ status: 'cancelled' })} />)
    expect(screen.getByText(/cancelled/i)).toBeInTheDocument()
  })

  it('renders Postponed status prominently', () => {
    render(<ShowDetail show={makeShow({ status: 'postponed' })} />)
    expect(screen.getByText(/postponed/i)).toBeInTheDocument()
  })

  it('renders door time', () => {
    render(<ShowDetail show={show} />)
    expect(screen.getByText(/7:00/i)).toBeInTheDocument()
  })

  it('renders price', () => {
    render(<ShowDetail show={show} />)
    expect(screen.getByText(/\$25/)).toBeInTheDocument()
  })

  it('renders age restriction', () => {
    render(<ShowDetail show={show} />)
    expect(screen.getByText(/21\+/)).toBeInTheDocument()
  })

  it('renders all flag indicators when set', () => {
    render(
      <ShowDetail
        show={makeShow({
          isPit: true,
          willSellOut: true,
          isDrinkTickets: true,
          isNoReentry: true,
        })}
      />,
    )
    expect(screen.getByText(/pit/i)).toBeInTheDocument()
    expect(screen.getByText(/sell out/i)).toBeInTheDocument()
    expect(screen.getByText(/drink/i)).toBeInTheDocument()
    expect(screen.getByText(/re-entry/i)).toBeInTheDocument()
  })

  it('shows sold out, matinee and benefit (with its cause)', () => {
    render(<ShowDetail show={makeShow({ isSoldOut: true, isMatinee: true, isBenefit: true, benefitCause: 'canned food drive' })} />)
    expect(screen.getByText('Sold out')).toBeInTheDocument()
    expect(screen.getByText('Matinee')).toBeInTheDocument()
    expect(screen.getByText(/Benefit: canned food drive/)).toBeInTheDocument()
  })

  it('shows an act note next to the band in the lineup', () => {
    render(<ShowDetail show={makeShow({ acts: [{ position: 0, band: makeBand({ id: 1, name: 'Black Flag' }), note: 'Greg Ginn, Max Zanelly' }] })} />)
    const act = screen.getByTestId('act-name').closest('li')!
    expect(act).toHaveTextContent('Black Flag')
    expect(act).toHaveTextContent('(Greg Ginn, Max Zanelly)')
    expect(screen.getByRole('link', { name: 'Black Flag' })).toBeInTheDocument()  // the note isn't part of the link
  })

  it('offers the show as a calendar file and as a Google Calendar event', () => {
    render(<ShowDetail show={makeShow({ id: 7, date: '2026-10-03' })} />)
    const ics = screen.getByRole('link', { name: 'Add to calendar' })
    expect(ics.getAttribute('href')).toMatch(/^data:text\/calendar/)
    expect(ics).toHaveAttribute('download', expect.stringMatching(/2026-10-03\.ics$/))
    const google = screen.getByRole('link', { name: 'Add to Google Calendar' })
    expect(google.getAttribute('href')).toMatch(/^https:\/\/calendar\.google\.com\/calendar\/render\?/)
    expect(google).toHaveAttribute('target', '_blank')
  })

  it.each(['cancelled', 'postponed'] as const)('leaves out the calendar links for a %s show', status => {
    render(<ShowDetail show={makeShow({ status })} />)
    expect(screen.queryByRole('link', { name: /calendar/i })).not.toBeInTheDocument()
  })

  it('shows the special event in a banner', () => {
    render(<ShowDetail show={makeShow({ specialEvent: 'Hardly Strictly Bluegrass' })} />)
    expect(screen.getByRole('note', { name: 'Special event' })).toHaveTextContent('Hardly Strictly Bluegrass')
  })

  it('has no special event banner when there is none', () => {
    render(<ShowDetail show={show} />)
    expect(screen.queryByRole('note', { name: 'Special event' })).not.toBeInTheDocument()
  })

  it('shows the special event and ticket provider when known', () => {
    render(<ShowDetail show={makeShow({ specialEvent: 'Hardly Strictly Bluegrass', ticketProvider: 'ticketweb' })} />)
    expect(screen.getByText('Hardly Strictly Bluegrass')).toBeInTheDocument()
    expect(screen.getByText(/Tickets via ticketweb/i)).toBeInTheDocument()
  })

  it('leaves the new details out when unknown', () => {
    render(<ShowDetail show={show} />)
    expect(screen.queryByText('Sold out')).not.toBeInTheDocument()
    expect(screen.queryByText(/Tickets via/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Benefit/)).not.toBeInTheDocument()
  })

  it('links to the venue, keeping the current filters from the URL', () => {
    currentParams = new URLSearchParams('genre=punk&region=sf')
    render(<ShowDetail show={show} />)
    for (const link of screen.getAllByRole('link', { name: 'The Fillmore' })) {
      expect(link).toHaveAttribute('href', `/venues/${show.venue.id}?genre=punk&region=sf`)
    }
  })
})
