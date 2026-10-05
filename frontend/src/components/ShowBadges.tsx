import type { ComponentType, ReactNode, SVGProps } from 'react'
import { ClockIcon, ExclamationTriangleIcon, FireIcon, HeartIcon, NoSymbolIcon, SunIcon, XCircleIcon } from '@heroicons/react/16/solid'
import type { HomeShow } from '@/lib/types'

/** 'compact' for the single-line row (no icons, so it stays on one line), 'card' for the grid, 'detail' for the Show page. */
export type BadgeSize = 'compact' | 'card' | 'detail'

type Icon = ComponentType<SVGProps<SVGSVGElement>>

const RED = 'bg-danger-soft text-danger'
const YELLOW = 'bg-warning-soft text-warning'
const NEUTRAL = 'bg-muted text-ink-soft'

function Badge({ icon: Icon, size, className, title, children }: {
  icon?: Icon; size: BadgeSize; className: string; title?: string; children: ReactNode
}) {
  const sizing = { compact: 'text-[11px] px-1.5 py-px', card: 'px-1.5 py-0.5', detail: 'text-sm px-2 py-1' }[size]
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full ${sizing} ${className}`} title={title}>
      {Icon && size !== 'compact' && <Icon className={`${size === 'detail' ? 'size-4' : 'size-3.5'} shrink-0`} />}
      {children}
    </span>
  )
}

export function StatusBadge({ status, size = 'card' }: { status: HomeShow['status']; size?: BadgeSize }) {
  if (status !== 'cancelled' && status !== 'postponed') return null
  const isCancelled = status === 'cancelled'
  const sizing = { compact: 'text-[10px] px-1.5 py-0.5', card: 'text-xs px-2 py-0.5', detail: 'text-sm px-3 py-1.5' }[size]
  return (
    <span className={`inline-flex items-center gap-1 ${sizing} font-bold uppercase tracking-wide rounded-full w-fit shrink-0 ${isCancelled ? RED : YELLOW}`}>
      {size !== 'compact' && (isCancelled
        ? <XCircleIcon className={`${size === 'detail' ? 'size-4' : 'size-3.5'} shrink-0`} />
        : <ClockIcon className={`${size === 'detail' ? 'size-4' : 'size-3.5'} shrink-0`} />)}
      {isCancelled ? 'Cancelled' : 'Postponed'}
    </span>
  )
}

export function Flags({ show, size, showBenefitCause = false }: { show: HomeShow; size: BadgeSize; showBenefitCause?: boolean }) {
  if (!(show.isSoldOut || show.isBenefit || show.isMatinee || show.willSellOut || show.isPit ||
        show.isDrinkTickets || show.isNoReentry)) return null
  const layout = { compact: 'gap-1 sm:justify-end', card: 'gap-1 text-xs', detail: 'gap-2' }[size]
  return (
    <div className={`flex flex-wrap ${layout}`}>
      {show.isSoldOut && <Badge icon={NoSymbolIcon} size={size} className={`font-semibold ${RED}`}>Sold out</Badge>}
      {show.isBenefit && (
        <Badge icon={HeartIcon} size={size} className="bg-success-soft text-success"
               title={showBenefitCause ? undefined : show.benefitCause ?? undefined}>
          {showBenefitCause && show.benefitCause ? `Benefit: ${show.benefitCause}` : 'Benefit'}
        </Badge>
      )}
      {show.isMatinee && (
        <Badge icon={SunIcon} size={size} className="bg-info-soft text-info">Matinee</Badge>
      )}
      {show.willSellOut && (
        <Badge icon={FireIcon} size={size} className="bg-hot-soft text-hot">
          Will Sell Out
        </Badge>
      )}
      {show.isPit && <Badge icon={ExclamationTriangleIcon} size={size} className={NEUTRAL}>Pit Warning</Badge>}
      {show.isDrinkTickets && <Badge size={size} className={NEUTRAL}>Drink Tickets</Badge>}
      {show.isNoReentry && <Badge size={size} className={NEUTRAL}>No Re-entry</Badge>}
    </div>
  )
}
