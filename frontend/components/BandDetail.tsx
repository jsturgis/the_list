'use client'

import Link from 'next/link'
import { GlobeAltIcon, MapPinIcon, MusicalNoteIcon } from '@heroicons/react/20/solid'
import ExternalLink from './ExternalLink'
import type { Band, Show } from '@/lib/types'
import SimilarBands from './SimilarBands'
import { formatDateShort } from '@/lib/format'
import { useBayAreaToday } from '@/lib/useBayAreaToday'

interface BandDetailProps {
  band: Band
  /** The Band's Upcoming Shows; dates before today (Bay Area time) are hidden in the browser. */
  upcomingShows: Show[]
  similarBands: Band[]
}

export default function BandDetail({ band, upcomingShows, similarBands }: BandDetailProps) {
  const today = useBayAreaToday()
  const shows = today ? upcomingShows.filter(s => s.date >= today) : upcomingShows

  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-6">
      {band.imageUrl && (
        // Hosts vary (and the site is a static export), so a plain <img> rather than next/image.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={band.imageUrl} alt={band.name} className="w-full max-h-72 object-cover rounded-lg" />
      )}
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-3xl font-bold text-ink">{band.name}</h1>
          {band.isLocal && (
            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded bg-accent-chip text-accent-chip-ink">
              <MapPinIcon className="size-3.5 shrink-0" />
              Local
            </span>
          )}
        </div>
        {band.genres.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {band.genres.map(g => (
              <span
                key={g}
                className="text-xs px-2 py-0.5 rounded-full bg-muted text-ink-soft"
              >
                {g}
              </span>
            ))}
          </div>
        )}
        {band.description && (
          <p className="mt-3 text-sm text-ink-soft">{band.description}</p>
        )}
      </header>

      {(band.spotifyUrl || band.soundcloudUrl || band.bandcampUrl || band.websiteUrl) && (
        <section className="flex flex-wrap gap-3">
          {band.spotifyUrl && (
            <ExternalLink
              href={band.spotifyUrl}
              icon={MusicalNoteIcon}
              className="text-sm px-3 py-1.5 rounded bg-green-600 text-white hover:bg-green-700"
            >
              Spotify
            </ExternalLink>
          )}
          {!band.spotifyUrl && band.soundcloudUrl && (
            <ExternalLink
              href={band.soundcloudUrl}
              icon={MusicalNoteIcon}
              className="text-sm px-3 py-1.5 rounded bg-orange-500 text-white hover:bg-orange-600"
            >
              SoundCloud
            </ExternalLink>
          )}
          {band.bandcampUrl && (
            <ExternalLink
              href={band.bandcampUrl}
              icon={MusicalNoteIcon}
              className="text-sm px-3 py-1.5 rounded bg-teal-600 text-white hover:bg-teal-700"
            >
              Bandcamp
            </ExternalLink>
          )}
          {band.websiteUrl && (
            <ExternalLink
              href={band.websiteUrl}
              icon={GlobeAltIcon}
              className="text-sm px-3 py-1.5 rounded bg-strong text-white hover:bg-strong-hover"
            >
              Website
            </ExternalLink>
          )}
        </section>
      )}

      {shows.length > 0 && (
        <section>
          <h2 className="text-base font-semibold mb-3 text-ink">
            Upcoming Shows
          </h2>
          <ul className="flex flex-col gap-2">
            {shows.map(show => (
              <li key={show.id}>
                <Link
                  href={`/shows/${show.id}`}
                  className="flex items-center justify-between gap-4 text-sm -mx-2 px-2 py-1 rounded hover:bg-muted"
                >
                  <span className="font-medium text-ink min-w-0 truncate">
                    {show.venue.name}
                    {' · '}
                    {show.venue.city}
                  </span>
                  <span className="text-ink-muted shrink-0">
                    {formatDateShort(show.date)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <SimilarBands bands={similarBands} />
    </article>
  )
}
