import type { ComponentType, ReactNode, SVGProps } from 'react'
import { ArrowTopRightOnSquareIcon } from '@heroicons/react/20/solid'

interface ExternalLinkProps {
  href: string
  className?: string
  /** Optional icon before the label (e.g. a globe for a website). */
  icon?: ComponentType<SVGProps<SVGSVGElement>>
  children: ReactNode
}

/** A link to another site: opens in a new tab and ends with an external-link icon. */
export default function ExternalLink({ href, className = '', icon: Icon, children }: ExternalLinkProps) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={`inline-flex items-center gap-1.5 ${className}`}>
      {Icon && <Icon className="size-4 shrink-0" />}
      {children}
      <ArrowTopRightOnSquareIcon className="size-3.5 shrink-0 opacity-70" />
    </a>
  )
}
