'use client'

import type { ReactNode } from 'react'
import { href } from '@/lib/basePath'
import { useQuery } from '@/lib/navigation'

interface VenueLinkProps {
  venueId: number
  className?: string
  children: ReactNode
}

/** Link to a Venue page that keeps the current filters, read in the browser (pages are static). */
export default function VenueLink({ venueId, className, children }: VenueLinkProps) {
  const qs = useQuery().toString()
  return <a href={href(qs ? `/venues/${venueId}/?${qs}` : `/venues/${venueId}/`)} className={className}>{children}</a>
}
