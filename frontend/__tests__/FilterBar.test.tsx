import { act, render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import FilterBar from '@/components/FilterBar'
import { replaceQuery } from '@/lib/navigation'

const props = { showCount: 10, dbTotal: 100, genres: ['punk', 'jazz'], regions: ['sf'], ages: ['a/a'], availableDates: [] }

describe('FilterBar genre note', () => {
  it('is hidden when no genre is selected', () => {
    render(<FilterBar {...props} />)
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('warns that unknown-genre shows are hidden when a genre is selected', () => {
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    expect(screen.getByRole('note')).toHaveTextContent(/no artist has a known genre are hidden/i)
    expect(screen.getByLabelText('Genre')).toHaveAccessibleDescription(/genre info/i)
  })
})

describe('FilterBar genre combobox', () => {
  it('applies the chosen genre to the URL', () => {
    render(<FilterBar {...props} />)
    const input = screen.getByRole('combobox', { name: 'Genre' })
    fireEvent.focus(input)
    fireEvent.click(screen.getByRole('option', { name: 'jazz' }))
    expect(window.location.search).toBe('?genre=jazz')
  })

  it('shows the active genre from the URL', () => {
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    expect(screen.getByRole('combobox', { name: 'Genre' })).toHaveValue('punk')
  })
})

describe('FilterBar clear filters', () => {
  it('resets every filter, including the genre combobox', () => {
    replaceQuery('genre=punk&region=sf&q=rose&free=1')
    render(<FilterBar {...props} />)
    expect(screen.getByRole('combobox', { name: 'Genre' })).toHaveValue('punk')

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(window.location.search).toBe('')
    expect(screen.getByRole('combobox', { name: 'Genre' })).toHaveValue('')
    expect(screen.getByLabelText('Search')).toHaveValue('')
    expect(screen.getByLabelText(/free only/i)).not.toBeChecked()
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
  })
})

describe('FilterBar search', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('applies the typed text to the URL as q', () => {
    render(<FilterBar {...props} />)
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'chapel' } })
    act(() => { vi.advanceTimersByTime(300) })
    expect(window.location.search).toBe('?q=chapel')
  })

  it('carries old band= and venue= links into the box and over to q', () => {
    replaceQuery('band=rose&venue=chapel&region=sf')
    render(<FilterBar {...props} />)
    expect(screen.getByLabelText('Search')).toHaveValue('rose chapel')
    act(() => { vi.advanceTimersByTime(300) })
    expect(window.location.search).toBe('?region=sf&q=rose+chapel')
  })
})

describe('FilterBar result count', () => {
  it('is a polite live region, so screen readers hear the count change', () => {
    render(<FilterBar {...props} />)
    const count = screen.getByRole('status')
    expect(count).toHaveTextContent('Showing 10 of 100 shows')
    expect(count).toHaveAttribute('aria-live', 'polite')
    expect(count).toHaveAttribute('aria-atomic', 'true')
  })
})

describe('FilterBar Advanced filters toggle', () => {
  it('says whether Advanced filters are open, and which controls it opens', () => {
    render(<FilterBar {...props} />)
    const toggle = screen.getByRole('button', { name: /advanced filters/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(document.getElementById(toggle.getAttribute('aria-controls')!)).toContainElement(screen.getByLabelText('From date'))
  })
})
