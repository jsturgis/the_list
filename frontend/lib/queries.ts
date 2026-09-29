export const FILTER_OPTIONS_QUERY = /* GraphQL */ `
  query GetFilterOptions {
    filterOptions {
      regions
      ages
      genres
      dates
    }
  }
`

export const SHOW_COUNT_QUERY = /* GraphQL */ `
  query GetShowCount {
    showCount
  }
`

export const SHOWS_QUERY = /* GraphQL */ `
  query GetShows($limit: Int, $offset: Int, $filters: ShowFilters) {
    shows(limit: $limit, offset: $offset, filters: $filters) {
      id
      date
      doorTime
      setTime
      venue {
        id
        name
        city
        region
        websiteUrl
        address
      }
      acts {
        position
        band {
          id
          name
          genres
          spotifyUrl
          soundcloudUrl
          bandcampUrl
        }
      }
      priceMin
      priceMax
      isFree
      ageRestriction
      status
      isRecommended
      willSellOut
      isPit
      isDrinkTickets
      isNoReentry
      notes
    }
  }
`

export const SHOW_QUERY = /* GraphQL */ `
  query GetShow($id: ID!) {
    show(id: $id) {
      id
      date
      doorTime
      setTime
      venue {
        id
        name
        city
        region
        websiteUrl
        address
        phone
        googleRating
        description
        wikipediaUrl
      }
      acts {
        position
        band {
          id
          name
          genres
          spotifyUrl
          soundcloudUrl
          bandcampUrl
        }
      }
      priceMin
      priceMax
      isFree
      ageRestriction
      status
      isRecommended
      willSellOut
      isPit
      isDrinkTickets
      isNoReentry
      notes
    }
  }
`

export const BAND_QUERY = /* GraphQL */ `
  query GetBand($id: ID!) {
    band(id: $id) {
      id
      name
      genres
      spotifyUrl
      soundcloudUrl
      bandcampUrl
    }
  }
`

export const BAND_SHOWS_QUERY = /* GraphQL */ `
  query GetBandShows($bandId: Int!) {
    shows(filters: { bandId: $bandId }, limit: 50) {
      id
      date
      doorTime
      venue {
        id
        name
        city
        region
      }
      acts {
        position
        band {
          id
          name
        }
      }
      priceMin
      isFree
      ageRestriction
      status
    }
  }
`

export const SIMILAR_BANDS_QUERY = /* GraphQL */ `
  query GetSimilarBands($bandId: ID!, $k: Int!) {
    similarBands(bandId: $bandId, k: $k) {
      id
      name
      genres
      spotifyUrl
      soundcloudUrl
      bandcampUrl
    }
  }
`

export const VENUE_QUERY = /* GraphQL */ `
  query GetVenue($id: ID!) {
    venue(id: $id) {
      id
      name
      address
      city
      region
      websiteUrl
      phone
      googleRating
      description
      wikipediaUrl
    }
  }
`

export const VENUE_SHOWS_QUERY = /* GraphQL */ `
  query GetVenueShows($venueId: Int!) {
    shows(filters: { venueId: $venueId }, limit: 100) {
      id
      date
      doorTime
      venue {
        id
        name
        city
        region
      }
      acts {
        position
        band {
          id
          name
          genres
        }
      }
      priceMin
      priceMax
      isFree
      ageRestriction
      status
      isRecommended
      willSellOut
      isPit
      isDrinkTickets
      isNoReentry
      notes
    }
  }
`

export const ALL_VENUES_STATIC_QUERY = /* GraphQL */ `
  query GetAllVenueIds {
    shows(limit: 500) {
      venue {
        id
      }
    }
  }
`

export const ALL_SHOWS_STATIC_QUERY = /* GraphQL */ `
  query GetAllShowIds {
    shows(limit: 500) {
      id
    }
  }
`

export const ALL_BANDS_STATIC_QUERY = /* GraphQL */ `
  query GetAllBandIds {
    shows(limit: 500) {
      acts {
        band {
          id
        }
      }
    }
  }
`
