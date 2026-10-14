import type { ReactNode } from 'react'
import { href } from '@/lib/basePath'

interface VenueLinkProps {
  /** The Venue's slug. */
  slug: string
  className?: string
  children: ReactNode
}

/** Link to a Venue page. It keeps the current filters: lib/keepFilters adds the page's query in the browser. */
export default function VenueLink({ slug, className, children }: VenueLinkProps) {
  return <a href={href(`/venues/${slug}/`)} data-keep-filters="" className={className}>{children}</a>
}
