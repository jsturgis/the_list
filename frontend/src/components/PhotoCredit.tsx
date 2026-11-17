import type { PhotoCredit as Credit } from '@/lib/types'

const creditLink = 'text-link underline underline-offset-2'

/**
 * A Band's or Venue's photo credit, the <figcaption> of its <figure> (DESIGN.md, "Band photo"): "Photo: <author>,
 * <licence>, via Wikimedia Commons", as a Commons photo's licence requires; "Photo via Discogs" or "Photo via
 * Bandcamp" for a photo from one of them, which has no author or licence to name. `className` places it.
 */
export default function PhotoCredit({ credit, className = '' }: { credit: Credit, className?: string }) {
  const caption = `text-xs text-ink-muted ${className}`
  if (credit.source !== 'Wikimedia Commons') {
    return (
      <figcaption className={caption}>
        Photo via <a href={credit.sourceUrl} target="_blank" rel="noopener noreferrer" className={creditLink}>{credit.source}</a>
      </figcaption>
    )
  }
  return (
    <figcaption className={caption}>
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
