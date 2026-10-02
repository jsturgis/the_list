'use client'

import { useEffect, type ReactNode } from 'react'
import { XMarkIcon } from '@heroicons/react/16/solid'

/** How long a toast stays up before it goes by itself. */
export const TOAST_MS = 8000

/**
 * A short confirmation at the bottom of the screen. Screen readers announce it politely; it closes itself
 * after a few seconds, or with its close button.
 */
export default function Toast({ children, onDismiss }: { children: ReactNode; onDismiss: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, TOAST_MS)
    return () => clearTimeout(timer)
  }, [onDismiss])

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-md items-start gap-3 rounded-lg bg-inverse px-4 py-3 text-sm text-on-inverse shadow-lg"
    >
      <div className="flex-1">{children}</div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="-m-1 rounded p-1 text-inverse-muted hover:text-on-inverse"
      >
        <XMarkIcon className="size-4" />
      </button>
    </div>
  )
}
