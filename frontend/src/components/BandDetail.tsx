import type { ReactNode } from 'react'
import { GlobeAltIcon, MapPinIcon } from '@heroicons/react/20/solid'
import { href } from '@/lib/basePath'
import ActionLinks, { ActionLink } from './ActionLinks'
import BandMembers from './BandMembers'
import ListeningLink from './ListeningLink'
import PageHeader from './PageHeader'
import SocialLinks from './SocialLinks'
import type { Band, PhotoCredit, Show } from '@/lib/types'
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
  // Up to 3 free services, then up to 3 paid ones, already ranked by the backend (app/band_links.py).
  const listening = (band.links ?? []).filter(l => l.group === 'listening')
  return (
    <article className="flex flex-col gap-6">
      {band.imageUrl && (
        <figure className="flex flex-col gap-1.5">
          {/* A stored photo is a site path ("/images/bands/…"), served under the base path; others are remote URLs. */}
          <img src={band.imageUrl.startsWith('/') ? href(band.imageUrl) : band.imageUrl} alt={band.name}
               className="w-full max-h-72 object-cover rounded-lg" />
          {band.imageCredit && <PhotoCreditLine credit={band.imageCredit} />}
        </figure>
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
          {listening.map(link => <ListeningLink key={link.service} link={link} />)}
          {band.websiteUrl && (
            <ActionLink href={band.websiteUrl} kind="custom" icon={GlobeAltIcon} external className="min-h-11 bg-strong text-on-inverse hover:bg-strong-hover">
              Website
            </ActionLink>
          )}
        </ActionLinks>
      )}

      <BandShows shows={upcomingShows} />

      <BandMembers members={band.members ?? []} />

      <SocialLinks links={band.links ?? []} />

      <SimilarBands bands={similarBands} />
    </article>
  )
}

const creditLink = 'text-link underline underline-offset-2'

/**
 * "Photo: <author>, <licence>, via Wikimedia Commons", as a Commons photo's licence requires; "Photo via Discogs"
 * for a Discogs photo, which has no author or licence to name.
 */
function PhotoCreditLine({ credit }: { credit: PhotoCredit }) {
  if (credit.source === 'Discogs') {
    return (
      <figcaption className="text-xs text-ink-muted">
        Photo via <a href={credit.sourceUrl} target="_blank" rel="noopener noreferrer" className={creditLink}>Discogs</a>
      </figcaption>
    )
  }
  return (
    <figcaption className="text-xs text-ink-muted">
      Photo: {credit.author ?? 'unknown author'}
      {credit.license && (
        <>, {credit.licenseUrl
          ? <a href={credit.licenseUrl} target="_blank" rel="noopener noreferrer license" className={creditLink}>{credit.license}</a>
          : credit.license}</>
      )}
      , via <a href={credit.sourceUrl} target="_blank" rel="noopener noreferrer" className={creditLink}>Wikimedia Commons</a>
    </figcaption>
  )
}
