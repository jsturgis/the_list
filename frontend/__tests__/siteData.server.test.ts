import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, it, expect, beforeAll } from 'vitest'
import { readExport } from '@/lib/siteData.server'
import type { ExportBand, ExportShow, ExportVenue } from '@/lib/types'

const venue = (id: number, name: string): ExportVenue => ({
  id, name, address: null, city: 'San Francisco', region: 'sf', websiteUrl: null, latitude: null, longitude: null,
  timezone: null, phone: null, googleRating: null, googlePlaceId: null, description: null, wikipediaUrl: null,
  neighborhood: null, venueType: null, nearestTransit: null, instagram: null, imageUrl: null,
  defaultAgeRestriction: null, isSoberSpace: null, isCashOnly: null, membershipRequired: null,
})
const band = (id: number, similar: number[] = []): ExportBand => ({
  id, name: `Band ${id}`, genres: [], spotifyUrl: null, soundcloudUrl: null, bandcampUrl: null, websiteUrl: null,
  imageUrl: null, isLocal: null, similar,
})
const show = (id: number, venueId: number, date: string, status = 'upcoming'): ExportShow => ({
  id, date, doorTime: '20:00:00', setTime: null, priceMin: null, priceMax: null, isFree: false, ageRestriction: 'a/a',
  status, isRecommended: false, willSellOut: false, isPit: false, isDrinkTickets: false, isNoReentry: false,
  notes: null, isMatinee: false, isSoldOut: false, ticketProvider: null, isBenefit: false, benefitCause: null,
  specialEvent: null, venueId, acts: [[id * 10, 0]],
})

let dir: string
beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), 'the-list-export-'))
  const files = {
    venues: [venue(1, 'The Fillmore'), venue(2, 'The Chapel')],
    bands: [band(10, [30, 20]), band(20), band(30)],
    shows: [show(3, 1, '2026-10-05'), show(1, 1, '2026-10-01'), show(2, 2, '2026-10-02', 'cancelled')],
    meta: { generatedAt: '', emailSubject: null, filterOptions: { regions: [], ages: [], genres: [], dates: [] }, totalUpcoming: 2 },
  }
  for (const [name, data] of Object.entries(files)) writeFileSync(join(dir, `${name}.json`), JSON.stringify(data))
})

describe('readExport', () => {
  it('finds a Show by id, with its Venue and Bands attached', () => {
    const data = readExport(dir)
    const s = data.show(1)!
    expect(s.venue.name).toBe('The Fillmore')
    expect(s.acts[0].band.name).toBe('Band 10')
    expect(data.show(999)).toBeUndefined()
  })

  it('finds a Venue by id', () => {
    const data = readExport(dir)
    expect(data.venue(2)?.name).toBe('The Chapel')
    expect(data.venue(999)).toBeUndefined()
  })

  it("lists a Venue's Upcoming Shows in date order", () => {
    const data = readExport(dir)
    expect(data.venueShows(1).map(s => s.id)).toEqual([1, 3])
    expect(data.venueShows(2)).toEqual([])  // cancelled only
  })

  it('provides every Show and Venue id for static generation', () => {
    const data = readExport(dir)
    expect(data.showIds()).toEqual(['1', '2', '3'])
    expect(data.venueIds()).toEqual(['1', '2'])
  })

  it('explains how to create the data when it is missing', () => {
    expect(() => readExport(join(dir, 'missing'))).toThrow(/app\.cli export/)
  })

  it("lists a Band's Upcoming Shows in date order", () => {
    const data = readExport(dir)
    expect(data.bandShows(30).map(s => s.id)).toEqual([3])
    expect(data.bandShows(20)).toEqual([])  // cancelled only
  })

  it('resolves Similar Bands in order', () => {
    const data = readExport(dir)
    expect(data.similarBands(10).map(b => b.name)).toEqual(['Band 30', 'Band 20'])
    expect(data.similarBands(20)).toEqual([])
  })

  it('provides every Band id for static generation', () => {
    expect(readExport(dir).bandIds()).toEqual(['10', '20', '30'])
  })
})
