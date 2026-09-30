'use client'

import Link from 'next/link'
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
          <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-50">{band.name}</h1>
          {band.isLocal && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              Local
            </span>
          )}
        </div>
        {band.genres.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {band.genres.map(g => (
              <span
                key={g}
                className="text-xs px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
              >
                {g}
              </span>
            ))}
          </div>
        )}
      </header>

      {(band.spotifyUrl || band.soundcloudUrl || band.bandcampUrl || band.websiteUrl) && (
        <section className="flex flex-wrap gap-3">
          {band.spotifyUrl && (
            <a
              href={band.spotifyUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm px-3 py-1.5 rounded bg-green-600 text-white hover:bg-green-700"
            >
              Spotify ↗
            </a>
          )}
          {!band.spotifyUrl && band.soundcloudUrl && (
            <a
              href={band.soundcloudUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm px-3 py-1.5 rounded bg-orange-500 text-white hover:bg-orange-600"
            >
              SoundCloud ↗
            </a>
          )}
          {band.bandcampUrl && (
            <a
              href={band.bandcampUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm px-3 py-1.5 rounded bg-teal-600 text-white hover:bg-teal-700"
            >
              Bandcamp ↗
            </a>
          )}
          {band.websiteUrl && (
            <a
              href={band.websiteUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm px-3 py-1.5 rounded bg-zinc-800 text-white hover:bg-zinc-700 dark:bg-zinc-700 dark:hover:bg-zinc-600"
            >
              Website ↗
            </a>
          )}
        </section>
      )}

      {shows.length > 0 && (
        <section>
          <h2 className="text-base font-semibold mb-3 text-zinc-900 dark:text-zinc-100">
            Upcoming Shows
          </h2>
          <ul className="flex flex-col gap-2">
            {shows.map(show => (
              <li key={show.id}>
                <Link
                  href={`/shows/${show.id}`}
                  className="flex items-center justify-between gap-4 text-sm -mx-2 px-2 py-1 rounded hover:bg-zinc-50 dark:hover:bg-zinc-800"
                >
                  <span className="font-medium text-zinc-900 dark:text-zinc-50 min-w-0 truncate">
                    {show.venue.name}
                    {' · '}
                    {show.venue.city}
                  </span>
                  <span className="text-zinc-500 dark:text-zinc-400 shrink-0">
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
