import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import BandDetail from '@/components/BandDetail'
import { hidePastShows } from '@/lib/upcomingShows'
import SimilarBands from '@/components/SimilarBands'
import { makeBand, makeShow, makeVenue } from './fixtures'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-01T19:00:00Z'))  // noon Pacific, Oct 1
})
afterEach(() => vi.useRealTimers())

const similar = [
  makeBand({ id: 10, name: 'LCD Soundsystem', genres: ['indie rock', 'electronic'] }),
  makeBand({ id: 11, name: 'Interpol', genres: ['post-punk', 'indie rock'] }),
]

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
    makeShow({ id: 1, date: '2026-10-03', acts: [{ position: 0, band }] }),
    makeShow({
      id: 2,
      date: '2026-10-05',
      venue: makeVenue({ name: 'Bottom of the Hill', city: 'San Francisco' }),
      acts: [{ position: 0, band }],
    }),
  ]

  // As on the Band page: the static page, then the browser hides dates that have passed (lib/upcomingShows).
  const renderBand = (b = band, shows = upcomingShows) => {
    const result = render(<BandDetail band={b} upcomingShows={shows} similarBands={similar} />)
    hidePastShows()
    return result
  }

  it('renders band name', () => {
    renderBand()
    expect(screen.getByRole('heading', { name: 'The Strokes' })).toBeInTheDocument()
  })

  it('renders genres', () => {
    renderBand()
    expect(screen.getByText(/garage rock/)).toBeInTheDocument()
  })

  it('renders Spotify link when available', () => {
    renderBand()
    expect(screen.getByRole('link', { name: /spotify/i })).toHaveAttribute('href', band.spotifyUrl)
  })

  it('renders SoundCloud as fallback when Spotify absent', () => {
    renderBand(makeBand({ spotifyUrl: null, soundcloudUrl: 'https://soundcloud.com/thestrokes' }), [])
    expect(screen.getByRole('link', { name: /soundcloud/i })).toHaveAttribute('href', 'https://soundcloud.com/thestrokes')
    expect(screen.queryByRole('link', { name: /spotify/i })).not.toBeInTheDocument()
  })

  it('renders upcoming shows list with show links', () => {
    renderBand()
    const showLinks = screen.getAllByRole('link').filter(l => l.getAttribute('href')?.startsWith('/shows/'))
    expect(showLinks.map(l => l.getAttribute('href'))).toEqual(['/shows/1/', '/shows/2/'])
  })

  it('hides shows dated before today (Bay Area time)', () => {
    renderBand(band, [makeShow({ id: 9, date: '2026-09-20', acts: [{ position: 0, band }] }), ...upcomingShows])
    const showLinks = screen.getAllByRole('link').filter(l => l.getAttribute('href')?.startsWith('/shows/'))
    expect(showLinks.map(l => l.getAttribute('href'))).toEqual(['/shows/1/', '/shows/2/'])
  })

  it('shows the image, Local tag and Website link when provided', () => {
    renderBand(makeBand({ id: 6, name: 'Locals', imageUrl: 'https://example.com/locals.jpg', isLocal: true, websiteUrl: 'https://locals.com' }), [])
    expect(screen.getByRole('img', { name: 'Locals' })).toHaveAttribute('src', 'https://example.com/locals.jpg')
    expect(screen.getByText('Local')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /website/i })).toHaveAttribute('href', 'https://locals.com')
  })

  it('leaves them out otherwise', () => {
    renderBand()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByText('Local')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /website/i })).not.toBeInTheDocument()
  })

  it('shows the description when known', () => {
    renderBand(makeBand({ id: 7, name: 'B.F.H.', description: 'Bilingual metal band from Fairfield, CA' }), [])
    expect(screen.getByText('Bilingual metal band from Fairfield, CA')).toBeInTheDocument()
  })

  it('lists the precomputed Similar Bands', () => {
    renderBand()
    expect(screen.getByRole('link', { name: /LCD Soundsystem/ })).toHaveAttribute('href', '/bands/10/')
  })
})

describe('SimilarBands', () => {
  it('links each similar band to its page, with its first genres', () => {
    render(<SimilarBands bands={similar} />)
    expect(screen.getByRole('link', { name: /LCD Soundsystem/i })).toHaveAttribute('href', '/bands/10/')
    expect(screen.getByRole('link', { name: /Interpol/i })).toHaveAttribute('href', '/bands/11/')
    expect(screen.getByText('post-punk, indie rock')).toBeInTheDocument()
  })

  it('renders nothing when there are no similar bands', () => {
    const { container } = render(<SimilarBands bands={[]} />)
    expect(container.querySelector('[data-testid="similar-bands"]')).not.toBeInTheDocument()
  })
})
