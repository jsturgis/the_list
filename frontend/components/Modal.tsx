'use client'

import React, { useEffect, useRef } from 'react'
import { XMarkIcon } from '@heroicons/react/20/solid'

interface ModalProps {
  /** Called when the dialog closes: the close button, Esc or a backdrop click. */
  onClose: () => void
  children: React.ReactNode
}

export default function Modal({ onClose, children }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={e => { if (e.target === ref.current) ref.current?.close() }}
      className="m-auto w-[calc(100%-2rem)] max-w-2xl max-h-[85vh] overflow-y-auto rounded-lg bg-surface text-ink p-6 backdrop:bg-black/50"
    >
      <button
        type="button"
        aria-label="Close"
        onClick={() => ref.current?.close()}
        className="absolute top-3 right-3 p-1.5 rounded text-ink-muted hover:text-ink-soft hover:bg-muted"
      >
        <XMarkIcon className="size-5" />
      </button>
      {children}
    </dialog>
  )
}
