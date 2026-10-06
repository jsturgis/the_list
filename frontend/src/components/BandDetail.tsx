import type { ReactNode } from 'react'
import { GlobeAltIcon, MapPinIcon, MusicalNoteIcon } from '@heroicons/react/20/solid'
import ActionLinks, { ActionLink } from './ActionLinks'
import PageHeader from './PageHeader'
import type { Band, Show } from '@/lib/types'
import BandShows from './BandShows'
import SimilarBands from './SimilarBands'

interface BandDetailProps {
  band: Band
  upcomingShows: Show[]
  similarBands: Band[]
  /** The alert bell (an island the Band page passes in), on the title's line. */
  bell?: ReactNode
}

export default function BandDetail({ band, upcomingShows, similarBands, bell }: BandDetailProps) {
  const brand = (bg: string) => `${bg} text-white`
  return (
    <article className="flex flex-col gap-6">
      {band.imageUrl && (
        <img src={band.imageUrl} alt={band.name} className="w-full max-h-72 object-cover rounded-lg" />
      )}

      <PageHeader title={band.name} aside={bell} subtitle={band.description ?? undefined}>
        {band.isLocal && (
          <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-accent-chip text-accent-chip-ink">
            <MapPinIcon className="size-3.5 shrink-0" />
            Local
          </span>
        )}
        {band.genres.map(g => (
          <span key={g} className="text-xs px-2 py-0.5 rounded-full bg-muted text-ink-soft">{g}</span>
        ))}
      </PageHeader>

      {(band.spotifyUrl || band.soundcloudUrl || band.bandcampUrl || band.websiteUrl) && (
        <ActionLinks>
          {band.spotifyUrl && (
            <ActionLink href={band.spotifyUrl} kind="custom" icon={MusicalNoteIcon} external className={brand('bg-green-700 hover:bg-green-800')}>
              Spotify
            </ActionLink>
          )}
          {!band.spotifyUrl && band.soundcloudUrl && (
            <ActionLink href={band.soundcloudUrl} kind="custom" icon={MusicalNoteIcon} external className={brand('bg-orange-700 hover:bg-orange-800')}>
              SoundCloud
            </ActionLink>
          )}
          {band.bandcampUrl && (
            <ActionLink href={band.bandcampUrl} kind="custom" icon={MusicalNoteIcon} external className={brand('bg-teal-700 hover:bg-teal-800')}>
              Bandcamp
            </ActionLink>
          )}
          {band.websiteUrl && (
            <ActionLink href={band.websiteUrl} kind="custom" icon={GlobeAltIcon} external className="bg-strong text-on-inverse hover:bg-strong-hover">
              Website
            </ActionLink>
          )}
        </ActionLinks>
      )}

      <BandShows shows={upcomingShows} />

      <SimilarBands bands={similarBands} />
    </article>
  )
}
