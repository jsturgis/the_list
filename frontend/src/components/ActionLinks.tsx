import type { AnchorHTMLAttributes, ComponentType, ReactNode, SVGProps } from 'react'
import { ArrowTopRightOnSquareIcon } from '@heroicons/react/20/solid'

const KINDS = {
  /** The page's main action (Tickets, See this week's shows). */
  primary: 'bg-accent text-on-accent hover:bg-accent-hover',
  /** Other actions (calendar, Wikipedia). */
  secondary: 'border border-line-strong bg-surface text-ink hover:bg-muted',
  /** Colours given by the caller (the neutral Website button). */
  custom: '',
}

interface ActionLinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  href: string
  kind?: keyof typeof KINDS
  icon?: ComponentType<SVGProps<SVGSVGElement>>
  /** Opens in a new tab, marked with the external-link icon. */
  external?: boolean
  children: ReactNode
}

/** A pill-shaped link that acts as a button (DESIGN.md, "Actions"). */
export function ActionLink({ kind = 'secondary', icon: Icon, external = false, className = '', children, ...rest }: ActionLinkProps) {
  return (
    <a
      {...rest}
      {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
      className={`inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold transition-colors ${KINDS[kind]} ${className}`}
    >
      {Icon && <Icon aria-hidden="true" className="size-4 shrink-0" />}
      {children}
      {external && <ArrowTopRightOnSquareIcon aria-hidden="true" className="size-3.5 shrink-0 opacity-70" />}
    </a>
  )
}

/** A row of ActionLinks, wrapping on narrow screens. */
export default function ActionLinks({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2">{children}</div>
}
