import { useEffect, type RefObject } from 'react'

/**
 * Closing behaviour for a small panel that opens from a button (Setup Alert, a Band or Venue page's bell): it
 * closes with Escape (focus goes back to the button), a click anywhere outside `container`, or when focus leaves
 * it (Tab past its last control), so it never stays open behind where the keyboard is.
 */
export function usePopover(
  open: boolean,
  close: () => void,
  container: RefObject<HTMLElement | null>,
  button: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      close()
      button.current?.focus()
    }
    const onPointer = (e: MouseEvent) => {
      if (container.current && !container.current.contains(e.target as Node)) close()
    }
    const onFocusOut = (e: FocusEvent) => {
      const next = e.relatedTarget as Node | null
      if (next && container.current && !container.current.contains(next)) close()
    }
    const el = container.current
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    el?.addEventListener('focusout', onFocusOut)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
      el?.removeEventListener('focusout', onFocusOut)
    }
  }, [open, close, container, button])
}
