import type { ComponentType, ReactNode, SVGProps } from 'react'

export interface Fact {
  icon: ComponentType<SVGProps<SVGSVGElement>>
  label: string
  value: ReactNode
}

/** Key facts as labelled values (DESIGN.md, "Key facts"): three across from `sm`, one per line on phones. */
export default function FactList({ facts }: { facts: Fact[] }) {
  return (
    <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {facts.map(({ icon: Icon, label, value }) => (
        <div key={label}>
          <dt className="flex items-center gap-1.5 text-xs text-ink-muted">
            <Icon aria-hidden="true" className="size-4 shrink-0 text-ink-faint" />
            {label}
          </dt>
          <dd className="mt-1 text-base font-semibold text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  )
}
