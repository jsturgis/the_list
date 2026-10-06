import type { HTMLAttributes, ReactNode } from 'react'

interface SectionProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  title: ReactNode
  /** A line under the heading, e.g. "3 of 20 alerts". */
  subtitle?: ReactNode
  /** The heading's id, for aria-labelledby; derived from a text title when omitted. */
  headingId?: string
  /** No panel around the content: for content that is already panels (lists of Show rows). */
  plain?: boolean
  children: ReactNode
}

const slug = (title: ReactNode) => `section-${String(title).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`

/**
 * A titled part of a page (DESIGN.md, "Sections"): a 24px bold h2 above a `surface` panel, named by that heading so
 * it's a landmark region for screen readers. Extra attributes (data-*, className) go on the <section>.
 */
export default function Section({ title, subtitle, headingId, plain = false, className = '', children, ...rest }: SectionProps) {
  const id = headingId ?? slug(title)
  return (
    <section
      aria-labelledby={id}
      className={`flex flex-col gap-3 ${className}`}
      {...rest}
    >
      {subtitle ? (
        <div className="flex flex-col gap-1">
          <h2 id={id} className="text-2xl font-bold text-ink">{title}</h2>
          <p className="text-sm text-ink-muted">{subtitle}</p>
        </div>
      ) : (
        <h2 id={id} className="text-2xl font-bold text-ink">{title}</h2>
      )}
      {plain ? children : <div className="flex flex-col gap-3 rounded-lg bg-surface p-5">{children}</div>}
    </section>
  )
}
