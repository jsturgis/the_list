import { render, screen, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import BandDetail from '@/components/BandDetail'
import { pastShowsStyle } from '@/lib/pastShows'
import SimilarBands from '@/components/SimilarBands'
import { makeBand, makeShow, makeVenue } from './fixtures'
import type { BandLink } from '@/lib/types'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-01T19:00:00Z'))  // noon Pacific, Oct 1
})
afterEach(() => vi.useRealTimers())

const similar = [
  makeBand({ id: 10, name: 'LCD Soundsystem', genres: ['indie rock', 'electronic'] }),
  makeBand({ id: 11, name: 'Interpol', genres: ['post-punk', 'indie rock'] }),
]

// The page's <head> adds this style: the export was made in early September, and the clock says Oct 1.
function hidePast() {
  const style = document.createElement('style')
  style.textContent = pastShowsStyle('2026-09-01')
  document.head.append(style)
}
afterEach(() => document.head.querySelectorAll('style').forEach(s => s.remove()))

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

  // As on the Band page: the built list, plus the CSS that hides dates that have passed (lib/pastShows).
  const renderBand = (b = band, shows = upcomingShows) => {
    const result = render(<BandDetail band={b} upcomingShows={shows} similarBands={similar} />)
    hidePast()
    return result
  }

  it('renders band name', () => {
    renderBand()
    expect(screen.getByRole('heading', { level: 1, name: 'The Strokes' })).toBeInTheDocument()
  })

  it('renders genres', () => {
    renderBand()
    expect(screen.getByText(/garage rock/)).toBeInTheDocument()
  })

  const link = (group: BandLink['group'], service: string, label: string, paid = false): BandLink =>
    ({ group, service, label, url: `https://${service}.example/the-strokes`, paid })

  it('shows the listening links in the order given: free services, then paid ones', () => {
    renderBand(makeBand({ links: [
      link('listening', 'spotify', 'Spotify'), link('listening', 'audiomack', 'Audiomack'),
      link('listening', 'apple_music', 'Apple Music', true),
    ] }), [])
    const buttons = screen.getAllByRole('link').filter(a => /Spotify|Audiomack|Apple Music/.test(a.textContent + (a.getAttribute('aria-label') ?? '')))
    expect(buttons.map(a => a.getAttribute('href'))).toEqual([
      'https://spotify.example/the-strokes', 'https://audiomack.example/the-strokes', 'https://apple_music.example/the-strokes',
    ])
  })

  it('names each logo button "Listen on <service>", marking paid ones, and opens it in a new tab', () => {
    renderBand(makeBand({ links: [
      link('listening', 'spotify', 'Spotify'), link('listening', 'youtube_music', 'YouTube Music'),
      link('listening', 'bandcamp', 'Bandcamp'), link('listening', 'soundcloud', 'SoundCloud'),
      link('listening', 'deezer', 'Deezer'), link('listening', 'apple_music', 'Apple Music', true),
      link('listening', 'amazon_music', 'Amazon Music', true), link('listening', 'tidal', 'Tidal', true),
      link('listening', 'qobuz', 'Qobuz', true),
    ] }), [])
    const names = [
      'Listen on Spotify', 'Listen on YouTube Music', 'Listen on Bandcamp', 'Listen on SoundCloud', 'Listen on Deezer',
      'Listen on Apple Music (subscription)', 'Listen on Amazon Music (subscription)', 'Listen on Tidal (subscription)',
      'Listen on Qobuz (subscription)',
    ]
    for (const name of names) {
      const button = screen.getByRole('link', { name })
      expect(button).toHaveAttribute('target', '_blank')
      expect(button).toHaveAttribute('rel', 'noopener noreferrer')
      expect(button).toHaveAttribute('title', name)  // the tooltip, for a logo without a label
      expect(button.textContent).toBe('')  // the logo alone
    }
    expect(screen.getByRole('link', { name: 'Listen on Tidal (subscription)' })).toHaveAttribute('href', 'https://tidal.example/the-strokes')
  })

  it("shows Qobuz's black wordmark in light mode and its white one in dark mode", () => {
    renderBand(makeBand({ links: [link('listening', 'qobuz', 'Qobuz', true)] }), [])
    const button = screen.getByRole('link', { name: 'Listen on Qobuz (subscription)' })
    expect(button.querySelector('img')).toHaveAttribute('src', '/icons/qobuz-light.png')
    const dark = button.querySelector('source')
    expect(dark).toHaveAttribute('media', '(prefers-color-scheme: dark)')
    expect(dark).toHaveAttribute('srcset', '/icons/qobuz-dark.png')
  })

  it('keeps a labelled button for a service without a logo', () => {
    renderBand(makeBand({ links: [
      link('listening', 'audiomack', 'Audiomack'), link('listening', 'napster', 'Napster', true),
    ] }), [])
    expect(screen.getByRole('link', { name: 'Audiomack' })).toHaveAttribute('href', 'https://audiomack.example/the-strokes')
    expect(screen.getByRole('link', { name: 'Audiomack' })).toHaveAttribute('target', '_blank')
    // Any service the site has no logo for, paid ones marked in the tooltip.
    expect(screen.getByRole('link', { name: 'Napster' })).toHaveAttribute('title', 'Napster (subscription)')
  })

  it('lists members under Members: current ones, then former ones under "Formerly"', () => {
    renderBand(makeBand({ members: [
      { name: 'Julian Casablancas', active: true }, { name: 'Old Drummer', active: false }, { name: 'Nick Valensi', active: true },
    ] }), [])
    const region = screen.getByRole('region', { name: 'Members' })
    const current = within(region).getByRole('list', { name: 'Current members' })
    expect(within(current).getAllByRole('listitem').map(li => li.textContent)).toEqual(['Julian Casablancas', 'Nick Valensi'])
    const former = within(region).getByRole('list', { name: 'Formerly' })
    expect(within(former).getAllByRole('listitem').map(li => li.textContent)).toEqual(['Old Drummer'])
  })

  it('lists only former members for a Band that has split up', () => {
    renderBand(makeBand({ members: [{ name: 'Old Drummer', active: false }] }), [])
    const region = screen.getByRole('region', { name: 'Members' })
    expect(within(region).queryByRole('list', { name: 'Current members' })).not.toBeInTheDocument()
    expect(within(region).getByRole('list', { name: 'Formerly' })).toHaveTextContent('Old Drummer')
  })

  it('has no Members section without members', () => {
    renderBand(makeBand({ members: [] }), [])
    expect(screen.queryByRole('region', { name: 'Members' })).not.toBeInTheDocument()
  })

  it('lists social profiles under Social', () => {
    renderBand(makeBand({ links: [
      link('listening', 'spotify', 'Spotify'), link('follow', 'instagram', 'Instagram'), link('follow', 'youtube', 'YouTube'),
    ] }), [])
    const region = screen.getByRole('region', { name: 'Social' })
    expect(within(region).getAllByRole('listitem').map(li => li.textContent)).toEqual(['Instagram', 'YouTube'])
    expect(within(region).getByRole('link', { name: /Instagram/ })).toHaveAttribute('href', 'https://instagram.example/the-strokes')
    expect(within(region).queryByText('Spotify')).not.toBeInTheDocument()  // listening links are buttons above
  })

  it('lists the website first under Social, not with the listening links', () => {
    renderBand(makeBand({ websiteUrl: 'https://thestrokes.example/', links: [
      link('listening', 'spotify', 'Spotify'), link('follow', 'instagram', 'Instagram'),
    ] }), [])
    const region = screen.getByRole('region', { name: 'Social' })
    expect(within(region).getAllByRole('listitem').map(li => li.textContent)).toEqual(['Website', 'Instagram'])
    const website = within(region).getByRole('link', { name: 'Website' })
    expect(website).toHaveAttribute('href', 'https://thestrokes.example/')
    expect(website).toHaveAttribute('target', '_blank')
    expect(screen.getAllByRole('link', { name: /website/i })).toHaveLength(1)
  })

  it('has a Social section with only the website for a Band without social profiles', () => {
    renderBand(makeBand({ websiteUrl: 'https://thestrokes.example/', links: [link('listening', 'spotify', 'Spotify')] }), [])
    const region = screen.getByRole('region', { name: 'Social' })
    expect(within(region).getAllByRole('listitem').map(li => li.textContent)).toEqual(['Website'])
  })

  it('has no Social section without social profiles or a website', () => {
    renderBand(makeBand({ websiteUrl: null, links: [link('listening', 'spotify', 'Spotify')] }), [])
    expect(screen.queryByRole('region', { name: 'Social' })).not.toBeInTheDocument()
  })

  it('renders upcoming shows list with show links', () => {
    renderBand()
    const showLinks = screen.getAllByRole('link').filter(l => l.getAttribute('href')?.startsWith('/shows/'))
    expect(showLinks.map(l => l.getAttribute('href'))).toEqual(['/shows/1/', '/shows/2/'])
  })

  it('lists upcoming shows as Show rows, each with its compact date and the Venue', () => {
    renderBand()
    const region = screen.getByRole('region', { name: 'Upcoming Shows' })
    expect([...region.querySelectorAll('time')].map(t => t.textContent)).toEqual(['SatOct 3', 'MonOct 5'])
    // A real list: one item per Show, each marked with its date for the past-date CSS.
    const items = within(within(region).getByRole('list')).getAllByRole('listitem')
    expect(items.map(li => li.getAttribute('data-show-date'))).toEqual(['2026-10-03', '2026-10-05'])
    const rows = within(region).getAllByRole('heading', { level: 3 })  // no date headings between
    expect(rows.map(h => h.querySelector('a')?.getAttribute('href'))).toEqual(['/shows/1/', '/shows/2/'])
    expect(region).toHaveTextContent('Bottom of the Hill')
  })

  it('leaves out Upcoming Shows when there are none', () => {
    renderBand(band, [])
    expect(screen.queryByRole('region', { name: 'Upcoming Shows' })).not.toBeInTheDocument()
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

  it('shows a stored photo from the site itself', () => {
    renderBand(makeBand({ id: 6, name: 'Locals', imageUrl: '/images/bands/6-3f9c2a1b7e.webp' }), [])
    // The site path goes through href(), which adds the base path in a build (none in tests).
    expect(screen.getByRole('img', { name: 'Locals' })).toHaveAttribute('src', '/images/bands/6-3f9c2a1b7e.webp')
  })

  it('anchors the cropped photo (banner and circle alike) at its focal point', () => {
    renderBand(makeBand({ id: 6, name: 'Locals', imageUrl: '/images/bands/6-3f9c2a1b7e.webp', imageFocus: { x: 12.5, y: 0 } }), [])
    expect(screen.getByRole('img', { name: 'Locals' })).toHaveStyle({ objectPosition: '12.5% 0%' })
  })

  it('anchors a photo without a focal point a little above centre', () => {
    renderBand(makeBand({ id: 6, name: 'Locals', imageUrl: '/images/bands/6-3f9c2a1b7e.webp', imageFocus: null }), [])
    expect(screen.getByRole('img', { name: 'Locals' })).toHaveStyle({ objectPosition: '50% 35%' })
  })

  it('credits a Wikimedia Commons photo under it, linking the licence and the photo page', () => {
    renderBand(makeBand({ id: 6, name: 'Locals', imageUrl: '/images/bands/6-3f9c2a1b7e.webp', imageCredit: {
      source: 'Wikimedia Commons', author: 'S. Bollmann', license: 'CC BY-SA 4.0', licenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0',
      sourceUrl: 'https://commons.wikimedia.org/wiki/File:Locals.jpg',
    } }), [])
    const caption = screen.getByRole('figure').querySelector('figcaption')!
    expect(caption).toHaveTextContent('Photo: S. Bollmann, CC BY-SA 4.0, via Wikimedia Commons')
    expect(within(caption).getByRole('link', { name: 'CC BY-SA 4.0' })).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/4.0')
    expect(within(caption).getByRole('link', { name: 'Wikimedia Commons' }))
      .toHaveAttribute('href', 'https://commons.wikimedia.org/wiki/File:Locals.jpg')
  })

  it('credits a Commons photo without a licence link or an author', () => {
    renderBand(makeBand({ name: 'Locals', imageUrl: '/images/bands/6-a.webp', imageCredit: {
      source: 'Wikimedia Commons', author: null, license: 'Public domain', licenseUrl: null, sourceUrl: 'https://commons.wikimedia.org/wiki/File:L.jpg',
    } }), [])
    expect(screen.getByRole('figure').querySelector('figcaption'))
      .toHaveTextContent('Photo: unknown author, Public domain, via Wikimedia Commons')
  })

  it('credits a Discogs photo "Photo via Discogs", linking the artist\'s page', () => {
    renderBand(makeBand({ name: 'Locals', imageUrl: '/images/bands/6-d.webp', imageCredit: {
      source: 'Discogs', author: null, license: null, licenseUrl: null, sourceUrl: 'https://www.discogs.com/artist/6-Locals',
    } }), [])
    const caption = screen.getByRole('figure').querySelector('figcaption')!
    expect(caption).toHaveTextContent(/^Photo via Discogs$/)
    expect(within(caption).getByRole('link', { name: 'Discogs' })).toHaveAttribute('href', 'https://www.discogs.com/artist/6-Locals')
  })

  it('shows the edition\'s photo without a credit', () => {
    renderBand(makeBand({ name: 'Locals', imageUrl: 'https://example.com/locals.jpg', imageCredit: null }), [])
    expect(screen.getByRole('figure').querySelector('figcaption')).toBeNull()
  })

  it('gives assistive tech the photo once, in the header beside the name, with its credit', () => {
    renderBand(makeBand({ name: 'Locals', imageUrl: '/images/bands/6-d.webp', imageCredit: {
      source: 'Discogs', author: null, license: null, licenseUrl: null, sourceUrl: 'https://www.discogs.com/artist/6-Locals',
    } }), [])
    const photos = screen.getAllByRole('img', { name: 'Locals' })
    expect(photos).toHaveLength(1)
    const heading = screen.getByRole('heading', { level: 1, name: 'Locals' })
    // One header holds the photo and the name (phones show them as one row); nothing hides the photo or its credit.
    expect(heading.closest('header')).toContainElement(photos[0])
    const caption = screen.getByRole('figure').querySelector('figcaption')!
    expect(caption).toBeVisible()
    expect(caption.closest('[aria-hidden="true"]')).toBeNull()
    expect(photos[0].closest('[aria-hidden="true"]')).toBeNull()
  })

  it('has no photo, figure or credit for a Band without a photo', () => {
    renderBand(makeBand({ name: 'Locals', imageUrl: null, imageCredit: null }), [])
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByRole('figure')).not.toBeInTheDocument()
    expect(screen.queryByText(/^Photo/)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Locals' })).toBeInTheDocument()
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
