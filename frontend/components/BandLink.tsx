import Link from 'next/link'
import type { ReactNode } from 'react'

interface BandLinkProps {
  bandId: number
  className?: string
  children: ReactNode
}

/** A link to a Band's page. */
export default function BandLink({ bandId, className, children }: BandLinkProps) {
  return (
    <Link href={`/bands/${bandId}`} className={className}>
      {children}
    </Link>
  )
}
