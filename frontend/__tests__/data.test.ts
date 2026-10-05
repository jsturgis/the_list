import { describe, it, expect } from 'vitest'
import { bayAreaToday, hydrateShows } from '@/lib/data'
import type { ExportBand, ExportShow, ExportVenue } from '@/lib/types'

const venue: ExportVenue = {
  id: 1, name: 'The Fillmore', address: '1805 Geary Blvd', city: 'San Francisco', region: 'sf', websiteUrl: null,
  latitude: null, longitude: null, timezone: null, phone: null, googleRating: null, googlePlaceId: 'ChIJ',
  description: null, wikipediaUrl: null, neighborhood: 'Western Addition', venueType: null, nearestTransit: null,
  instagram: null, imageUrl: null, defaultAgeRestriction: null, isSoberSpace: null, isCashOnly: null,
  membershipRequired: null,
}
const band = (id: number, name: string): ExportBand => ({
  id, name, genres: ['punk'], spotifyUrl: null, soundcloudUrl: null, bandcampUrl: null,
  websiteUrl: null, imageUrl: null, isLocal: null, description: null, similar: [],
})
const show = (id: number, date: string, status = 'upcoming', acts: ExportShow['acts'] = [[10, 0], [11, 1]]): ExportShow => ({
  id, date, doorTime: '20:00:00', setTime: null, priceMin: 15, priceMax: 20, isFree: false, ageRestriction: '21+',
  status, isRecommended: false, willSellOut: false, isPit: false, isDrinkTickets: false, isNoReentry: false,
  notes: null, isMatinee: false, isSoldOut: false, ticketProvider: null, ticketUrl: null, isBenefit: false, benefitCause: null,
  specialEvent: null, venueId: 1, acts,
})

describe('hydrateShows', () => {
  it('attaches the Venue and Bands to each Show, keeping Act order', () => {
    const [s] = hydrateShows([show(5, '2026-10-01', 'upcoming', [[11, 1], [10, 0]])], [venue], [band(10, 'Headliner'), band(11, 'Support')])
    expect(s.venue.name).toBe('The Fillmore')
    expect(s.venue.neighborhood).toBe('Western Addition')
    expect(s.acts.map(a => [a.position, a.band.name])).toEqual([[0, 'Headliner'], [1, 'Support']])
  })

  it('keeps an act note when the export has one', () => {
    const [s] = hydrateShows([show(5, '2026-10-01', 'upcoming', [[10, 0, 'Greg Ginn, Max Zanelly'], [11, 1]])], [venue], [band(10, 'Black Flag'), band(11, 'Support')])
    expect(s.acts.map(a => a.note)).toEqual(['Greg Ginn, Max Zanelly', undefined])
  })
})

describe('bayAreaToday', () => {
  it('uses the Pacific date even when UTC is already tomorrow', () => {
    // 6:15pm PDT Sep 29 = 01:15 UTC Sep 30
    expect(bayAreaToday(new Date('2026-09-30T01:15:00Z'))).toBe('2026-09-29')
  })

  it('matches UTC in the morning', () => {
    expect(bayAreaToday(new Date('2026-09-29T16:00:00Z'))).toBe('2026-09-29')
  })
})
