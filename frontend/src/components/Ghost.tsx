/**
 * Ghost placeholders (DESIGN.md, "Loading"): grey shapes that pulse where content will appear while it loads from
 * Supabase. They're hidden from screen readers; each use carries a visually hidden "Loading …" label instead.
 */

/** A bar standing in for a line of text. Set its width (and height for larger text) with `className`. */
export function GhostLine({ className = '' }: { className?: string }) {
  return <span aria-hidden="true" className={`block h-4 rounded-full bg-line motion-safe:animate-pulse ${className}`} />
}

/** The visually hidden label that tells screen readers what's loading. */
export function LoadingLabel({ children }: { children: string }) {
  return <span className="sr-only">{children}</span>
}

/** Ghost rows of a list, with the list's dividers: a name, and a small icon button at the end. */
export function GhostRows({ rows = 3, label }: { rows?: number; label: string }) {
  const widths = ['w-40', 'w-24', 'w-32']
  return (
    <div data-ghost="">
      <LoadingLabel>{label}</LoadingLabel>
      <ul aria-hidden="true" className="flex flex-col divide-y divide-line-subtle">
        {Array.from({ length: rows }, (_, i) => (
          <li key={i} className="flex items-center justify-between gap-4 py-3">
            <GhostLine className={widths[i % widths.length]} />
            <GhostLine className="size-4" />
          </li>
        ))}
      </ul>
    </div>
  )
}
