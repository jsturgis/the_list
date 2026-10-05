import type { ReactNode } from 'react'
import { href } from '@/lib/basePath'

interface BandLinkProps {
  bandId: number
  className?: string
  children: ReactNode
}

/** A link to a Band's page. */
export default function BandLink({ bandId, className, children }: BandLinkProps) {
  return (
    <a href={href(`/bands/${bandId}/`)} className={className}>
      {children}
    </a>
  )
}
