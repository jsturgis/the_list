import type { ReactNode } from 'react'

interface PageHeaderProps {
  /** A line above the title, e.g. a Show's date and status. */
  eyebrow?: ReactNode
  title: ReactNode
  /** Something on the title's line, at the right (a Show's date and calendar links); it wraps under on phones. */
  aside?: ReactNode
  /** A line below the title, e.g. "at The Fillmore · San Francisco". */
  subtitle?: ReactNode
  /** Chips or badges under the subtitle (genres, "Local", a Venue's rules). */
  children?: ReactNode
}

/** Every page's header (DESIGN.md, "Page header"): the one h1 style, with an optional eyebrow and subtitle. */
export default function PageHeader({ eyebrow, title, aside, subtitle, children }: PageHeaderProps) {
  return (
    <header className="flex flex-col gap-2">
      {eyebrow && <div className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">{eyebrow}</div>}
      {aside ? (
        <div className="relative flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <h1 className="text-3xl text-ink sm:text-4xl">{title}</h1>
          <div className="flex items-center gap-2 text-sm text-ink-muted">{aside}</div>
        </div>
      ) : (
        <h1 className="text-3xl text-ink sm:text-4xl">{title}</h1>
      )}
      {subtitle && <p className="text-lg text-ink-soft">{subtitle}</p>}
      {children && <div className="flex flex-wrap items-center gap-2 pt-1">{children}</div>}
    </header>
  )
}
