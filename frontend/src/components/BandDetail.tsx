import type { ReactNode } from 'react'
import { GlobeAltIcon, MapPinIcon, MusicalNoteIcon } from '@heroicons/react/20/solid'
import ActionLinks, { ActionLink } from './ActionLinks'
import BandLinks from './BandLinks'
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

// The three services with a brand-coloured button; the rest are outline buttons.
const BRAND: Record<string, string> = {
  spotify: 'bg-green-700 hover:bg-green-800 text-white',
  soundcloud: 'bg-orange-700 hover:bg-orange-800 text-white',
  bandcamp: 'bg-teal-700 hover:bg-teal-800 text-white',
}

export default function BandDetail({ band, upcomingShows, similarBands, bell }: BandDetailProps) {
  // Up to 3 free services, then up to 3 paid ones, already ranked by the backend (app/band_links.py).
  const listening = (band.links ?? []).filter(l => l.group === 'listening')
  return (
    <article className="flex flex-col gap-6">
      {band.imageUrl && (
        <img src={band.imageUrl} alt={band.name} className="w-full max-h-72 object-cover rounded-lg" />
      )}

      <PageHeader title={band.name} aside={bell} asideBesideTitle subtitle={band.description ?? undefined}>
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

      {(listening.length > 0 || band.websiteUrl) && (
        <ActionLinks>
          {listening.map(link => (
            <ActionLink
              key={link.service}
              href={link.url}
              icon={MusicalNoteIcon}
              external
              {...(BRAND[link.service] ? { kind: 'custom', className: BRAND[link.service] } : { kind: 'secondary' })}
              title={link.paid ? `${link.label} (subscription)` : undefined}
            >
              {link.label}
            </ActionLink>
          ))}
          {band.websiteUrl && (
            <ActionLink href={band.websiteUrl} kind="custom" icon={GlobeAltIcon} external className="bg-strong text-on-inverse hover:bg-strong-hover">
              Website
            </ActionLink>
          )}
        </ActionLinks>
      )}

      <BandShows shows={upcomingShows} />

      <BandLinks links={band.links ?? []} />

      <SimilarBands bands={similarBands} />
    </article>
  )
}
