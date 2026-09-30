'use client'

import React, { createContext, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'

// Lets links inside the modal replace the current history entry instead of pushing, so
// moving between Bands in the modal keeps a single entry and one close dismisses it.
export const InModalContext = createContext(false)

export default function Modal({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  return (
    <dialog
      ref={ref}
      onClose={() => router.back()}
      onClick={e => { if (e.target === ref.current) ref.current?.close() }}
      className="m-auto w-[calc(100%-2rem)] max-w-2xl max-h-[85vh] overflow-y-auto rounded-lg bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-50 p-6 backdrop:bg-black/50"
    >
      <button
        type="button"
        aria-label="Close"
        onClick={() => ref.current?.close()}
        className="absolute top-3 right-3 text-xl leading-none px-2 py-1 rounded text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100 dark:hover:text-zinc-300 dark:hover:bg-zinc-800"
      >
        ×
      </button>
      <InModalContext.Provider value={true}>{children}</InModalContext.Provider>
    </dialog>
  )
}
