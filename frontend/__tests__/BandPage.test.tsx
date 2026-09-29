import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { graphql } from 'msw/graphql'
import { HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

const api = graphql.link('http://localhost:8000/graphql')
import BandDetail from '@/components/BandDetail'
import SimilarBands from '@/components/SimilarBands'
import { makeBand, makeShow, makeVenue } from './fixtures'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('BandDetail', () => {
  const band = makeBand({
    id: 5,
    name: 'The Strokes',
    genres: ['indie rock', 'garage rock'],
    spotifyUrl: 'https://open.spotify.com/artist/0epOFNiUfyON9EYx7Tpr6V',
    soundcloudUrl: null,
    bandcampUrl: null,
  })

  const upcomingShows = [
    makeShow({ id: 1, acts: [{ position: 0, band }] }),
    makeShow({
      id: 2,
      date: '2026-10-05',
      venue: makeVenue({ name: 'Bottom of the Hill', city: 'San Francisco' }),
      acts: [{ position: 0, band }],
    }),
  ]

  it('renders band name', () => {
    render(<BandDetail band={band} upcomingShows={upcomingShows} />)
    expect(screen.getByRole('heading', { name: 'The Strokes' })).toBeInTheDocument()
  })

  it('renders genres', () => {
    render(<BandDetail band={band} upcomingShows={upcomingShows} />)
    expect(screen.getByText(/indie rock/)).toBeInTheDocument()
    expect(screen.getByText(/garage rock/)).toBeInTheDocument()
  })

  it('renders Spotify link when available', () => {
    render(<BandDetail band={band} upcomingShows={upcomingShows} />)
    expect(screen.getByRole('link', { name: /spotify/i })).toHaveAttribute(
      'href',
      band.spotifyUrl,
    )
  })

  it('renders SoundCloud as fallback when Spotify absent', () => {
    const scBand = makeBand({
      spotifyUrl: null,
      soundcloudUrl: 'https://soundcloud.com/thestrokes',
    })
    render(<BandDetail band={scBand} upcomingShows={[]} />)
    expect(screen.getByRole('link', { name: /soundcloud/i })).toHaveAttribute(
      'href',
      'https://soundcloud.com/thestrokes',
    )
    expect(screen.queryByRole('link', { name: /spotify/i })).not.toBeInTheDocument()
  })

  it('renders upcoming shows list with venue links', () => {
    render(<BandDetail band={band} upcomingShows={upcomingShows} />)
    const showLinks = screen.getAllByRole('link').filter(l =>
      l.getAttribute('href')?.startsWith('/shows/'),
    )
    expect(showLinks).toHaveLength(2)
    expect(showLinks[0]).toHaveAttribute('href', '/shows/1')
    expect(showLinks[1]).toHaveAttribute('href', '/shows/2')
  })
})

describe('SimilarBands', () => {
  const similarBands = [
    makeBand({ id: 10, name: 'LCD Soundsystem', genres: ['indie rock', 'electronic'] }),
    makeBand({ id: 11, name: 'Interpol', genres: ['post-punk', 'indie rock'] }),
  ]

  it('renders similar bands after live API call', async () => {
    server.use(
      api.query('GetSimilarBands', () =>
        HttpResponse.json({ data: { similarBands } }),
      ),
    )
    render(<SimilarBands bandId={5} />)
    await waitFor(() => {
      expect(screen.getByText('LCD Soundsystem')).toBeInTheDocument()
      expect(screen.getByText('Interpol')).toBeInTheDocument()
    })
  })

  it('links each similar band to its page', async () => {
    server.use(
      api.query('GetSimilarBands', () =>
        HttpResponse.json({ data: { similarBands } }),
      ),
    )
    render(<SimilarBands bandId={5} />)
    await waitFor(() => {
      expect(screen.getByRole('link', { name: /LCD Soundsystem/i })).toHaveAttribute(
        'href',
        '/bands/10',
      )
    })
  })

  it('renders nothing when no similar bands returned', async () => {
    server.use(
      api.query('GetSimilarBands', () =>
        HttpResponse.json({ data: { similarBands: [] } }),
      ),
    )
    const { container } = render(<SimilarBands bandId={5} />)
    await waitFor(() => {
      expect(container.querySelector('[data-testid="similar-bands"]')).not.toBeInTheDocument()
    })
  })
})
