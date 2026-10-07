import type { ReactNode } from 'react'
import { MapPinIcon } from '@heroicons/react/20/solid'
import { href } from '@/lib/basePath'
import { objectPosition } from '@/lib/photoFocus'
import ActionLinks from './ActionLinks'
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
      <PageHeader title={band.name} aside={bell} asideBesideTitle subtitle={band.description ?? undefined}
                  media={band.imageUrl && <BandPhoto band={band} imageUrl={band.imageUrl} />}>
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

      {listening.length > 0 && (
        <ActionLinks>
          {listening.map(link => <ListeningLink key={link.service} link={link} />)}
        </ActionLinks>
      )}

      <BandShows shows={upcomingShows} />

      <BandMembers members={band.members ?? []} />

      <SocialLinks links={band.links ?? []} websiteUrl={band.websiteUrl} />

      <SimilarBands bands={similarBands} />
    </article>
  )
}

/**
 * The Band's photo, one <img> laid out by breakpoint: on phones a 64px circle at the left of the name, its credit on
 * a line under them; from `sm`, full column width above the name, its credit under it (DESIGN.md, "Band photo").
 * The <figure> is `display: contents`, so the photo and credit are PageHeader's title-line items.
 */
function BandPhoto({ band, imageUrl }: { band: Band, imageUrl: string }) {
  return (
    <figure className="contents">
      {/* A stored photo is a site path ("/images/bands/…"), served under the base path; others are remote URLs. */}
      {/* Both crops (the circle and the banner) are anchored at the photo's focal point, so they keep its faces. */}
      <img src={imageUrl.startsWith('/') ? href(imageUrl) : imageUrl} alt={band.name}
           style={{ objectPosition: objectPosition(band.imageFocus) }}
           className={`size-16 shrink-0 rounded-full object-cover sm:h-auto sm:max-h-72 sm:w-full sm:basis-full sm:rounded-lg ${band.imageCredit ? '' : 'sm:mb-6'}`} />
      {band.imageCredit && <PhotoCreditLine credit={band.imageCredit} />}
    </figure>
  )
}

const creditLink = 'text-link underline underline-offset-2'
// Under the photo from `sm`; on phones, on its own line under the photo and the name.
const creditLine = 'order-last mt-2 basis-full text-xs text-ink-muted sm:order-none sm:mt-1.5 sm:mb-6'

/**
 * "Photo: <author>, <licence>, via Wikimedia Commons", as a Commons photo's licence requires; "Photo via Discogs"
 * for a Discogs photo, which has no author or licence to name.
 */
function PhotoCreditLine({ credit }: { credit: PhotoCredit }) {
  if (credit.source === 'Discogs') {
    return (
      <figcaption className={creditLine}>
        Photo via <a href={credit.sourceUrl} target="_blank" rel="noopener noreferrer" className={creditLink}>Discogs</a>
      </figcaption>
    )
  }
  return (
    <figcaption className={creditLine}>
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
