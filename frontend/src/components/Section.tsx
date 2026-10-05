import type { HTMLAttributes, ReactNode } from 'react'

interface SectionProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  title: ReactNode
  /** The heading's id, for aria-labelledby; derived from a text title when omitted. */
  headingId?: string
  /** No panel: for content that is already panels (lists of Show rows). */
  plain?: boolean
  children: ReactNode
}

const slug = (title: ReactNode) => `section-${String(title).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`

/**
 * A titled part of a page (DESIGN.md, "Sections"): a `surface` panel with a 24px bold h2, named by that heading so
 * it's a landmark region for screen readers. Extra attributes (data-*, className) go on the <section>.
 */
export default function Section({ title, headingId, plain = false, className = '', children, ...rest }: SectionProps) {
  const id = headingId ?? slug(title)
  return (
    <section
      aria-labelledby={id}
      className={`flex flex-col gap-3 ${plain ? '' : 'rounded-lg bg-surface p-5'} ${className}`}
      {...rest}
    >
      <h2 id={id} className="text-2xl font-bold text-ink">{title}</h2>
      {children}
    </section>
  )
}
