'use client'

import { useEffect, useId, useRef, useState } from 'react'

interface ComboboxProps {
  id: string
  options: string[]
  /** The applied value ('' for none). */
  value: string
  /** Called with an option when one is chosen (or typed exactly), and with '' when cleared. */
  onChange: (value: string) => void
  placeholder?: string
  'aria-describedby'?: string
}

const inputClass =
  'w-full h-9 rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 py-1.5 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400'

/**
 * Text input with a filterable suggestion list rendered at the input's width (ARIA combobox pattern).
 * Matching is case-insensitive "contains" on the current text. Partial text never changes `value`; leaving the input
 * with unmatched text reverts it to the applied value.
 */
export default function Combobox({ id, options, value, onChange, placeholder, ...aria }: ComboboxProps) {
  const listId = useId()
  const listRef = useRef<HTMLUListElement>(null)
  const [text, setText] = useState(value)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)

  // Follow external changes to the applied value (e.g. "Clear filters"), but keep the user's
  // own text when it already names that value.
  const [prevValue, setPrevValue] = useState(value)
  if (value !== prevValue) {
    setPrevValue(value)
    if (text.trim().toLowerCase() !== value.toLowerCase()) setText(value)
  }

  // The list always reflects what's in the box; an empty box shows every option.
  const query = text.trim().toLowerCase()
  const matches = query ? options.filter(o => o.toLowerCase().includes(query)) : options

  // Keep the highlighted option in view. Re-run on text changes too: typing can put a different
  // option at the same index.
  useEffect(() => {
    if (active >= 0) {
      listRef.current?.children[active]?.scrollIntoView?.({ block: 'nearest' })
    }
  }, [active, query])

  const choose = (option: string) => {
    setText(option)
    setOpen(false)
    setActive(-1)
    if (option !== value) onChange(option)
  }

  const close = () => {
    setOpen(false)
    setActive(-1)
    setText(value)
  }

  const onType = (next: string) => {
    setText(next)
    setOpen(true)
    const typed = next.trim().toLowerCase()
    if (!typed) {
      setActive(-1)
      if (value) onChange('')
      return
    }
    // Highlight (and so scroll to) an exact match among the options the list will now show.
    const nextMatches = options.filter(o => o.toLowerCase().includes(typed))
    const exactIndex = nextMatches.findIndex(o => o.toLowerCase() === typed)
    setActive(exactIndex)
    if (exactIndex >= 0 && nextMatches[exactIndex] !== value) onChange(nextMatches[exactIndex])
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) setOpen(true)
      if (matches.length === 0) return
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActive(i => (i + step + matches.length) % matches.length)
    } else if (e.key === 'Enter' && open && active >= 0) {
      e.preventDefault()
      choose(matches[active])
    } else if (e.key === 'Escape' && open) {
      e.preventDefault()
      close()
    }
  }

  const activeId = open && active >= 0 ? `${listId}-${active}` : undefined

  return (
    <div className="relative">
      <input
        id={id}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={activeId}
        aria-describedby={aria['aria-describedby']}
        autoComplete="off"
        placeholder={placeholder}
        value={text}
        onChange={e => onType(e.target.value)}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        onBlur={close}
        onKeyDown={onKeyDown}
        className={inputClass}
      />
      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto rounded border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 py-1 text-sm shadow-lg"
        >
          {matches.length === 0 ? (
            <li className="px-2 py-1.5 text-zinc-500 dark:text-zinc-400">No matches</li>
          ) : (
            matches.map((option, i) => (
              <li
                key={option}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={option === value}
                // Keep focus in the input so blur doesn't close the list before the click lands.
                onMouseDown={e => e.preventDefault()}
                onClick={() => choose(option)}
                onMouseEnter={() => setActive(i)}
                className={`px-2 py-1.5 cursor-pointer break-words ${
                  i === active ? 'bg-zinc-100 dark:bg-zinc-700' : ''
                } ${option === value ? 'font-medium text-amber-700 dark:text-amber-400' : 'text-zinc-900 dark:text-zinc-100'}`}
              >
                {option}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}
