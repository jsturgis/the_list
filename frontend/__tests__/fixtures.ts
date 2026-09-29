import type { Show, Band, Venue } from '@/lib/types'

export const makeVenue = (overrides: Partial<Venue> = {}): Venue => ({
  id: 1,
  name: 'The Fillmore',
  address: '1805 Geary Blvd, San Francisco, CA 94115',
  city: 'San Francisco',
  region: 'sf',
  websiteUrl: 'https://www.thefillmore.com',
  latitude: 37.7842,
  longitude: -122.4324,
  timezone: 'America/Los_Angeles',
  phone: null,
  googleRating: 4.7,
  description: 'Historic SF venue.',
  wikipediaUrl: null,
  ...overrides,
})

export const makeBand = (overrides: Partial<Band> = {}): Band => ({
  id: 1,
  name: 'Test Band',
  genres: ['indie rock', 'alternative'],
  spotifyUrl: 'https://open.spotify.com/artist/abc',
  soundcloudUrl: null,
  bandcampUrl: null,
  ...overrides,
})

export const makeShow = (overrides: Partial<Show> = {}): Show => ({
  id: 1,
  date: '2026-10-03',
  doorTime: '19:00:00',
  setTime: '20:00:00',
  venue: makeVenue(),
  acts: [{ position: 0, band: makeBand() }],
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
  ...overrides,
})

export const makeShowFixtures = (): Show[] => [
  // Steve's Pick in SF, 21+, $25-$30
  makeShow({
    id: 1,
    date: '2026-10-03',
    venue: makeVenue({ id: 1, name: 'The Fillmore', city: 'San Francisco', region: 'sf' }),
    acts: [
      { position: 0, band: makeBand({ id: 1, name: 'Headliner Band', genres: ['rock'] }) },
      { position: 1, band: makeBand({ id: 2, name: 'Support Act', genres: ['indie'] }) },
    ],
    priceMin: 25, priceMax: 30, isFree: false,
    ageRestriction: '21+',
    isRecommended: true,
    willSellOut: true,
  }),
  // East Bay, all ages, free
  makeShow({
    id: 2,
    date: '2026-10-03',
    venue: makeVenue({ id: 2, name: 'Cornerstone', city: 'Berkeley', region: 'east_bay' }),
    acts: [{ position: 0, band: makeBand({ id: 3, name: 'East Bay Band', genres: ['punk'] }) }],
    priceMin: 0, priceMax: 0, isFree: true,
    ageRestriction: 'a/a',
  }),
  // North Bay, 18+, $15-$20
  makeShow({
    id: 3,
    date: '2026-10-04',
    venue: makeVenue({ id: 3, name: 'Lagunitas', city: 'Petaluma', region: 'north_bay' }),
    acts: [{ position: 0, band: makeBand({ id: 4, name: 'North Bay Band', genres: ['folk'] }) }],
    priceMin: 15, priceMax: 20, isFree: false,
    ageRestriction: '18+',
  }),
  // South Bay, 21+, $35-$50
  makeShow({
    id: 4,
    date: '2026-10-04',
    venue: makeVenue({ id: 4, name: 'Venue SJ', city: 'San Jose', region: 'south_bay' }),
    acts: [{ position: 0, band: makeBand({ id: 5, name: 'South Bay Band', genres: ['electronic'] }) }],
    priceMin: 35, priceMax: 50, isFree: false,
    ageRestriction: '21+',
  }),
  // Santa Cruz, all ages, $10
  makeShow({
    id: 5,
    date: '2026-10-05',
    venue: makeVenue({ id: 5, name: 'The Catalyst', city: 'Santa Cruz', region: 'santa_cruz' }),
    acts: [{ position: 0, band: makeBand({ id: 6, name: 'Santa Cruz Band', genres: ['surf rock'] }) }],
    priceMin: 10, priceMax: 10, isFree: false,
    ageRestriction: 'a/a',
  }),
  // SF, pit warning, drink tickets
  makeShow({
    id: 6,
    date: '2026-10-05',
    venue: makeVenue({ id: 6, name: 'Bottom of the Hill', city: 'San Francisco', region: 'sf' }),
    acts: [{ position: 0, band: makeBand({ id: 7, name: 'Heavy Band', genres: ['metal'] }) }],
    priceMin: 20, priceMax: 25, isFree: false,
    ageRestriction: '21+',
    isPit: true, isDrinkTickets: true,
  }),
  // Cancelled show
  makeShow({
    id: 7,
    date: '2026-10-05',
    venue: makeVenue({ id: 7, name: 'Great American', city: 'San Francisco', region: 'sf' }),
    acts: [{ position: 0, band: makeBand({ id: 8, name: 'Cancelled Band', genres: ['indie'] }) }],
    priceMin: 30, priceMax: 30, isFree: false,
    ageRestriction: '21+',
    status: 'cancelled',
  }),
  // Postponed show
  makeShow({
    id: 8,
    date: '2026-10-06',
    venue: makeVenue({ id: 8, name: 'Slim\'s', city: 'San Francisco', region: 'sf' }),
    acts: [{ position: 0, band: makeBand({ id: 9, name: 'Postponed Band', genres: ['jazz'] }) }],
    priceMin: 22, priceMax: 22, isFree: false,
    ageRestriction: '21+',
    status: 'postponed',
  }),
  // No reentry flag
  makeShow({
    id: 9,
    date: '2026-10-06',
    venue: makeVenue({ id: 9, name: 'Outside Lands', city: 'San Francisco', region: 'sf' }),
    acts: [{ position: 0, band: makeBand({ id: 10, name: 'Festival Band', genres: ['pop'] }) }],
    priceMin: 100, priceMax: 150, isFree: false,
    ageRestriction: 'a/a',
    isNoReentry: true, willSellOut: true,
  }),
  // East Bay, Steve's Pick, all ages, free
  makeShow({
    id: 10,
    date: '2026-10-07',
    venue: makeVenue({ id: 10, name: 'Eli\'s Mile High Club', city: 'Oakland', region: 'east_bay' }),
    acts: [{ position: 0, band: makeBand({ id: 11, name: 'Oakland Blues Band', genres: ['blues'] }) }],
    priceMin: 0, priceMax: 0, isFree: true,
    ageRestriction: 'a/a',
    isRecommended: true,
  }),
  // SF, 12+, $5
  makeShow({
    id: 11,
    date: '2026-10-07',
    venue: makeVenue({ id: 11, name: 'The Chapel', city: 'San Francisco', region: 'sf' }),
    acts: [
      { position: 0, band: makeBand({ id: 12, name: 'Family Band', genres: ['folk'] }) },
      { position: 1, band: makeBand({ id: 13, name: 'Opening Act', genres: ['americana'] }) },
    ],
    priceMin: 5, priceMax: 5, isFree: false,
    ageRestriction: '12+',
  }),
  // East Bay, 21+, no price
  makeShow({
    id: 12,
    date: '2026-10-08',
    venue: makeVenue({ id: 12, name: 'The New Parish', city: 'Oakland', region: 'east_bay' }),
    acts: [{ position: 0, band: makeBand({ id: 14, name: 'Hip Hop Act', genres: ['hip hop'] }) }],
    priceMin: null, priceMax: null, isFree: false,
    ageRestriction: '21+',
  }),
  // SF, 16+, $12
  makeShow({
    id: 13,
    date: '2026-10-08',
    venue: makeVenue({ id: 13, name: 'Rickshaw Stop', city: 'San Francisco', region: 'sf' }),
    acts: [{ position: 0, band: makeBand({ id: 15, name: 'Teen Band', genres: ['emo'] }) }],
    priceMin: 12, priceMax: 12, isFree: false,
    ageRestriction: '16+',
  }),
  // South Bay, free, all ages
  makeShow({
    id: 14,
    date: '2026-10-09',
    venue: makeVenue({ id: 14, name: 'Venue MV', city: 'Mountain View', region: 'south_bay' }),
    acts: [{ position: 0, band: makeBand({ id: 16, name: 'Amphitheater Band', genres: ['country'] }) }],
    priceMin: 0, priceMax: 0, isFree: true,
    ageRestriction: 'a/a',
  }),
  // SF, 6+, $8
  makeShow({
    id: 15,
    date: '2026-10-09',
    venue: makeVenue({ id: 15, name: 'GAMH', city: 'San Francisco', region: 'sf' }),
    acts: [{ position: 0, band: makeBand({ id: 17, name: 'Kids Band', genres: ['indie pop'] }) }],
    priceMin: 8, priceMax: 8, isFree: false,
    ageRestriction: '6+',
  }),
  // North Bay, Steve's Pick, 21+, $40
  makeShow({
    id: 16,
    date: '2026-10-10',
    venue: makeVenue({ id: 16, name: 'Mystic Theatre', city: 'Petaluma', region: 'north_bay' }),
    acts: [{ position: 0, band: makeBand({ id: 18, name: 'NorCal Star', genres: ['country rock'] }) }],
    priceMin: 40, priceMax: 40, isFree: false,
    ageRestriction: '21+',
    isRecommended: true,
  }),
  // Santa Cruz, 18+, $25
  makeShow({
    id: 17,
    date: '2026-10-10',
    venue: makeVenue({ id: 17, name: 'Moe\'s Alley', city: 'Santa Cruz', region: 'santa_cruz' }),
    acts: [{ position: 0, band: makeBand({ id: 19, name: 'SC Act', genres: ['reggae'] }) }],
    priceMin: 25, priceMax: 25, isFree: false,
    ageRestriction: '18+',
  }),
  // SF, 5+, free
  makeShow({
    id: 18,
    date: '2026-10-11',
    venue: makeVenue({ id: 18, name: 'SFMOMA', city: 'San Francisco', region: 'sf' }),
    acts: [{ position: 0, band: makeBand({ id: 20, name: 'Museum Act', genres: ['classical'] }) }],
    priceMin: 0, priceMax: 0, isFree: true,
    ageRestriction: '5+',
  }),
  // East Bay, 18+, $18
  makeShow({
    id: 19,
    date: '2026-10-11',
    venue: makeVenue({ id: 19, name: 'Freight & Salvage', city: 'Berkeley', region: 'east_bay' }),
    acts: [{ position: 0, band: makeBand({ id: 21, name: 'Folk Duo', genres: ['folk', 'bluegrass'] }) }],
    priceMin: 18, priceMax: 18, isFree: false,
    ageRestriction: '18+',
  }),
  // SF, all ages, $50-$75, Steve's Pick
  makeShow({
    id: 20,
    date: '2026-10-12',
    venue: makeVenue({ id: 20, name: 'Chase Center', city: 'San Francisco', region: 'sf' }),
    acts: [
      { position: 0, band: makeBand({ id: 22, name: 'Big Arena Act', genres: ['pop', 'r&b'] }) },
      { position: 1, band: makeBand({ id: 23, name: 'Arena Opener', genres: ['pop'] }) },
    ],
    priceMin: 50, priceMax: 75, isFree: false,
    ageRestriction: 'a/a',
    isRecommended: true,
    willSellOut: true,
    isNoReentry: true,
  }),
]
