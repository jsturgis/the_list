import { useEffect, useState, type ReactNode } from 'react'
import { XMarkIcon } from '@heroicons/react/16/solid'

/** How long a toast stays up before it goes by itself. */
export const TOAST_MS = 8000

/**
 * A short confirmation at the bottom of the screen. Screen readers announce it politely; it closes itself
 * after a few seconds, or with its close button. It stays while the pointer or keyboard focus is on it, so its
 * link and close button can be reached.
 */
export default function Toast({ children, onDismiss }: { children: ReactNode; onDismiss: () => void }) {
  const [held, setHeld] = useState({ hover: false, focus: false })
  const paused = held.hover || held.focus

  useEffect(() => {
    if (paused) return
    const timer = setTimeout(onDismiss, TOAST_MS)
    return () => clearTimeout(timer)
  }, [onDismiss, paused])

  return (
    <div
      role="status"
      aria-live="polite"
      onMouseEnter={() => setHeld(h => ({ ...h, hover: true }))}
      onMouseLeave={() => setHeld(h => ({ ...h, hover: false }))}
      onFocus={() => setHeld(h => ({ ...h, focus: true }))}
      onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setHeld(h => ({ ...h, focus: false })) }}
      className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-md items-start gap-3 rounded-lg bg-inverse px-4 py-3 text-sm text-on-inverse shadow-lg"
    >
      <div className="flex-1">{children}</div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="-m-1 rounded-full p-1 text-inverse-muted hover:text-on-inverse"
      >
        <XMarkIcon className="size-4" />
      </button>
    </div>
  )
}
