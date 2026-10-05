import { GlobeAltIcon, MapPinIcon, MusicalNoteIcon } from '@heroicons/react/20/solid'
import ExternalLink from './ExternalLink'
import type { Band, Show } from '@/lib/types'
import BandShows from './BandShows'
import SimilarBands from './SimilarBands'

interface BandDetailProps {
  band: Band
  upcomingShows: Show[]
  similarBands: Band[]
}

export default function BandDetail({ band, upcomingShows, similarBands }: BandDetailProps) {

  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-6">
      {band.imageUrl && (
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
              className="text-sm px-3 py-1.5 rounded bg-green-700 text-white hover:bg-green-800"
            >
              Spotify
            </ExternalLink>
          )}
          {!band.spotifyUrl && band.soundcloudUrl && (
            <ExternalLink
              href={band.soundcloudUrl}
              icon={MusicalNoteIcon}
              className="text-sm px-3 py-1.5 rounded bg-orange-700 text-white hover:bg-orange-800"
            >
              SoundCloud
            </ExternalLink>
          )}
          {band.bandcampUrl && (
            <ExternalLink
              href={band.bandcampUrl}
              icon={MusicalNoteIcon}
              className="text-sm px-3 py-1.5 rounded bg-teal-700 text-white hover:bg-teal-800"
            >
              Bandcamp
            </ExternalLink>
          )}
          {band.websiteUrl && (
            <ExternalLink
              href={band.websiteUrl}
              icon={GlobeAltIcon}
              className="text-sm px-3 py-1.5 rounded bg-strong text-on-inverse hover:bg-strong-hover"
            >
              Website
            </ExternalLink>
          )}
        </section>
      )}

      <BandShows shows={upcomingShows} />

      <SimilarBands bands={similarBands} />
    </article>
  )
}
