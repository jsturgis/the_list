import { describe, it, expect } from 'vitest'
import { formatDateCompact, mapsHref, telHref, ticketProviderLabel } from '@/lib/format'

describe('formatDateCompact', () => {
  it('splits a date into weekday and month-day', () => {
    expect(formatDateCompact('2026-10-03')).toEqual({ weekday: 'Sat', monthDay: 'Oct 3' })
    expect(formatDateCompact('2026-12-31')).toEqual({ weekday: 'Thu', monthDay: 'Dec 31' })
  })
})

describe('ticketProviderLabel', () => {
  it('names the known providers', () => {
    expect(['box_office', 'door_only', 'free_entry', 'ticketweb', 'bottomofthehill'].map(ticketProviderLabel))
      .toEqual(['Box office', 'At the door', 'Free entry', 'TicketWeb', 'Bottom of the Hill'])
  })

  it('shows an unknown provider with spaces for underscores', () => {
    expect(ticketProviderLabel('will_call')).toBe('will call')
  })
})

describe('telHref', () => {
  it('adds +1 to a 10-digit US number', () => {
    expect(telHref('(415) 872-5745')).toBe('tel:+14158725745')
  })

  it('handles a leading 1', () => {
    expect(telHref('1-415-872-5745')).toBe('tel:+14158725745')
  })

  it('keeps an explicit country code', () => {
    expect(telHref('+44 20 7946 0958')).toBe('tel:+442079460958')
  })
})

describe('mapsHref', () => {
  const venue = { name: 'The Fillmore', address: '1805 Geary Blvd, San Francisco, CA 94115', city: 'San Francisco' }

  it('uses the place ID when present', () => {
    const url = new URL(mapsHref({ ...venue, googlePlaceId: 'ChIJabc' }))
    expect(url.origin + url.pathname).toBe('https://www.google.com/maps/search/')
    expect(url.searchParams.get('api')).toBe('1')
    expect(url.searchParams.get('query_place_id')).toBe('ChIJabc')
    expect(url.searchParams.get('query')).toBe('The Fillmore')
  })

  it('falls back to searching the address', () => {
    const url = new URL(mapsHref({ ...venue, googlePlaceId: null }))
    expect(url.searchParams.get('query')).toBe('1805 Geary Blvd, San Francisco, CA 94115')
    expect(url.searchParams.has('query_place_id')).toBe(false)
  })
})
