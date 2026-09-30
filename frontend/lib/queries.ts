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
