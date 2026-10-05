import type { ReactNode } from 'react'
import { href } from '@/lib/basePath'

interface VenueLinkProps {
  venueId: number
  className?: string
  children: ReactNode
}

/** Link to a Venue page. It keeps the current filters: lib/keepFilters adds the page's query in the browser. */
export default function VenueLink({ venueId, className, children }: VenueLinkProps) {
  return <a href={href(`/venues/${venueId}/`)} data-keep-filters="" className={className}>{children}</a>
}
