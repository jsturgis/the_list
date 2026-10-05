import { render, screen, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import VenueDetail from '@/components/VenueDetail'
import { pastShowsStyle } from '@/lib/pastShows'
import type { Show } from '@/lib/types'
import { makeBand, makeShow, makeVenue } from './fixtures'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-01T19:00:00Z'))  // noon Pacific, Oct 1
})
afterEach(() => vi.useRealTimers())

const venue = makeVenue({
  id: 7, name: 'The Catalyst', city: 'Santa Cruz', region: 'santa_cruz', neighborhood: 'Downtown Santa Cruz',
  nearestTransit: 'Santa Cruz Metro Center (2 min walk)', instagram: '@catalystclub',
  imageUrl: 'https://example.com/catalyst.jpg', defaultAgeRestriction: 'varies',
  isSoberSpace: false, isCashOnly: true, membershipRequired: null, description: "Santa Cruz's long-running rock club.",
})
// As on the Venue page: the built list, plus the CSS that hides dates that have passed (lib/pastShows).
const renderVenue = (v = venue, shows: Show[] = []) => {
  const result = render(<VenueDetail venue={v} upcomingShows={shows} />)
  hidePast()
  return result
}
const show = (id: number, date: string, name: string) =>
  makeShow({ id, date, venue, acts: [{ position: 0, band: makeBand({ id, name }) }] })

// The page's <head> adds this style: the export was made in early September, and the clock says Oct 1.
function hidePast() {
  const style = document.createElement('style')
  style.textContent = pastShowsStyle('2026-09-01')
  document.head.append(style)
}
afterEach(() => document.head.querySelectorAll('style').forEach(s => s.remove()))

describe('VenueDetail', () => {
  it('shows the neighborhood, transit, Instagram and image', () => {
    renderVenue()
    expect(screen.getByText(/Downtown Santa Cruz/)).toBeInTheDocument()
    expect(screen.getByText(/Santa Cruz Metro Center \(2 min walk\)/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '@catalystclub' })).toHaveAttribute('href', 'https://www.instagram.com/catalystclub/')
    expect(screen.getByRole('img', { name: 'The Catalyst' })).toHaveAttribute('src', 'https://example.com/catalyst.jpg')
  })

  it('shows the usual age policy', () => {
    renderVenue()
    expect(screen.getByText(/Varies by show/)).toBeInTheDocument()
  })

  it('shows rule indicators only when true', () => {
    renderVenue()
    expect(screen.getByText('Cash only')).toBeInTheDocument()
    expect(screen.queryByText('Sober space')).not.toBeInTheDocument()
    expect(screen.queryByText('Membership required')).not.toBeInTheDocument()
  })

  it('shows the description when present', () => {
    renderVenue()
    expect(screen.getByText("Santa Cruz's long-running rock club.")).toBeInTheDocument()
  })

  it('leaves out details the venue does not have', () => {
    renderVenue(makeVenue({ id: 8, name: 'Plain Venue' }))
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByText(/instagram/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Usual ages/)).not.toBeInTheDocument()
  })

  it('lists upcoming shows grouped by date, hiding dates before today (Bay Area time)', () => {
    renderVenue(venue, [
      show(1, '2026-09-30', 'Yesterday Band'), show(2, '2026-10-01', 'Tonight Band'), show(3, '2026-10-04', 'Weekend Band'),
    ])
    const list = screen.getByRole('region', { name: 'Upcoming Shows' })
    expect(within(list).getByText('Tonight Band')).toBeInTheDocument()
    expect(within(list).getByText('Weekend Band')).toBeInTheDocument()
    expect(within(list).getByText('Yesterday Band')).not.toBeVisible()
    expect(within(list).getByText(/Thursday, October 1/i)).toBeInTheDocument()
  })

  it('says so when there are no upcoming shows', () => {
    renderVenue(venue, [show(1, '2026-09-30', 'Yesterday Band')])
    expect(screen.getByText('No upcoming shows.')).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Upcoming Shows' })).not.toBeInTheDocument()
  })
})
