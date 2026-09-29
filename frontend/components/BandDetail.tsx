import Link from 'next/link'
import type { Band, Show } from '@/lib/types'
import SimilarBands from './SimilarBands'
import { formatDateShort } from '@/lib/format'

interface BandDetailProps {
  band: Band
  upcomingShows: Show[]
}

export default function BandDetail({ band, upcomingShows }: BandDetailProps) {
  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-6">
      <header>
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-50">{band.name}</h1>
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

      {(band.spotifyUrl || band.soundcloudUrl || band.bandcampUrl) && (
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
        </section>
      )}

      {upcomingShows.length > 0 && (
        <section>
          <h2 className="text-base font-semibold mb-3 text-zinc-900 dark:text-zinc-100">
            Upcoming Shows
          </h2>
          <ul className="flex flex-col gap-2">
            {upcomingShows.map(show => (
              <li key={show.id} className="flex items-center justify-between gap-4 text-sm -mx-2 px-2 py-1 rounded hover:bg-zinc-50 dark:hover:bg-zinc-800">
                <span className="font-medium text-zinc-900 dark:text-zinc-50 min-w-0 truncate">
                  <Link href={`/venues/${show.venue.id}`} className="hover:underline">
                    {show.venue.name}
                  </Link>
                  {' · '}
                  {show.venue.city}
                </span>
                <Link
                  href={`/shows/${show.id}`}
                  className="text-zinc-500 dark:text-zinc-400 shrink-0 hover:underline"
                >
                  {formatDateShort(show.date)}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <SimilarBands bandId={band.id} />
    </article>
  )
}
