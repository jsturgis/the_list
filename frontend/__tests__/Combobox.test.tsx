import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { useState } from 'react'
import Combobox from '@/components/Combobox'

const OPTIONS = ['punk', 'post-punk', 'jazz', 'free jazz']

function Harness({ initial = '', onChange = vi.fn() }: { initial?: string; onChange?: (v: string) => void }) {
  const [value, setValue] = useState(initial)
  return (
    <>
      <label htmlFor="genre">Genre</label>
      <Combobox id="genre" options={OPTIONS} value={value} onChange={v => { onChange(v); setValue(v) }} />
      <button>elsewhere</button>
    </>
  )
}

const input = () => screen.getByRole('combobox', { name: 'Genre' })
const optionNames = () => within(screen.getByRole('listbox')).queryAllByRole('option').map(o => o.textContent)

describe('Combobox', () => {
  it('opens the full list on focus', async () => {
    render(<Harness />)
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    await userEvent.click(input())
    expect(input()).toHaveAttribute('aria-expanded', 'true')
    expect(optionNames()).toEqual(OPTIONS)
  })

  it('filters by case-insensitive contains', async () => {
    render(<Harness />)
    await userEvent.type(input(), 'PUN')
    expect(optionNames()).toEqual(['punk', 'post-punk'])
  })

  it('shows a message when nothing matches', async () => {
    render(<Harness />)
    await userEvent.type(input(), 'zzz')
    expect(optionNames()).toEqual([])
    expect(screen.getByRole('listbox')).toHaveTextContent('No matches')
  })

  it('chooses an option by click', async () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    await userEvent.type(input(), 'jaz')
    await userEvent.click(screen.getByRole('option', { name: 'free jazz' }))
    expect(onChange).toHaveBeenLastCalledWith('free jazz')
    expect(input()).toHaveValue('free jazz')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('chooses an option with arrow keys and Enter', async () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    await userEvent.type(input(), 'pun')
    await userEvent.keyboard('{ArrowDown}{ArrowDown}')
    expect(input()).toHaveAttribute('aria-activedescendant', screen.getByRole('option', { name: 'post-punk' }).id)
    await userEvent.keyboard('{Enter}')
    expect(onChange).toHaveBeenLastCalledWith('post-punk')
  })

  it('applies an exact typed match without choosing from the list', async () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    await userEvent.type(input(), 'Jazz')
    expect(onChange).toHaveBeenLastCalledWith('jazz')
  })

  it('does not change the value for partial text, and reverts it on Escape or blur', async () => {
    const onChange = vi.fn()
    render(<Harness initial="jazz" onChange={onChange} />)
    await userEvent.clear(input())
    onChange.mockClear()
    await userEvent.type(input(), 'pu')
    expect(onChange).not.toHaveBeenCalled()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    await userEvent.type(input(), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'elsewhere' }))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('clears the value when the text is emptied', async () => {
    const onChange = vi.fn()
    render(<Harness initial="jazz" onChange={onChange} />)
    await userEvent.clear(input())
    expect(onChange).toHaveBeenLastCalledWith('')
  })

  it('marks the applied option as selected', async () => {
    render(<Harness initial="jazz" />)
    await userEvent.click(input())
    expect(screen.getByRole('option', { name: 'jazz' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('option', { name: 'free jazz' })).toHaveAttribute('aria-selected', 'false')
  })

  it('keeps filtering by the typed text after it matches a value', async () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    await userEvent.type(input(), 'PUNK')
    expect(onChange).toHaveBeenLastCalledWith('punk')
    expect(input()).toHaveValue('PUNK')
    expect(optionNames()).toEqual(['punk', 'post-punk'])
  })

  it('filters by the applied value when reopened', async () => {
    render(<Harness initial="jazz" />)
    await userEvent.click(input())
    expect(optionNames()).toEqual(['jazz', 'free jazz'])
  })

  describe('exact match while typing', () => {
    const scrollIntoView = vi.fn()
    afterEach(() => {
      scrollIntoView.mockClear()
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView
    })

    it('highlights the exact match and scrolls it into view', async () => {
      Element.prototype.scrollIntoView = scrollIntoView
      render(<Harness />)
      await userEvent.type(input(), 'free jazz')
      const match = screen.getByRole('option', { name: 'free jazz' })
      expect(input()).toHaveAttribute('aria-activedescendant', match.id)
      expect(scrollIntoView.mock.contexts.at(-1)).toBe(match)
    })

    it('finds the exact match even when other options contain the text', async () => {
      Element.prototype.scrollIntoView = scrollIntoView
      render(<Harness />)
      await userEvent.type(input(), 'jazz')  // matches "jazz" and "free jazz"
      expect(input()).toHaveAttribute('aria-activedescendant', screen.getByRole('option', { name: 'jazz' }).id)
    })

    it('clears the highlight when the text no longer matches exactly', async () => {
      render(<Harness />)
      await userEvent.type(input(), 'jazzy')
      expect(input()).not.toHaveAttribute('aria-activedescendant')
    })
  })
})
