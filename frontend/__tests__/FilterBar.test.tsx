import { act, render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import FilterBar from '@/components/FilterBar'

let params = new URLSearchParams()
const replace = vi.fn()
vi.mock('next/navigation', () => ({
  useSearchParams: () => params,
  useRouter: () => ({ push: vi.fn(), replace }),
  usePathname: () => '/',
}))

const props = { showCount: 10, dbTotal: 100, genres: ['punk', 'jazz'], regions: ['sf'], ages: ['a/a'], availableDates: [] }

describe('FilterBar genre note', () => {
  beforeEach(() => { params = new URLSearchParams(); replace.mockClear() })

  it('is hidden when no genre is selected', () => {
    render(<FilterBar {...props} />)
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('warns that unknown-genre shows are hidden when a genre is selected', () => {
    params = new URLSearchParams('genre=punk')
    render(<FilterBar {...props} />)
    expect(screen.getByRole('note')).toHaveTextContent(/no artist has a known genre are hidden/i)
    expect(screen.getByLabelText('Genre')).toHaveAccessibleDescription(/genre info/i)
  })
})

describe('FilterBar genre combobox', () => {
  beforeEach(() => { params = new URLSearchParams(); replace.mockClear() })

  it('applies the chosen genre to the URL', () => {
    render(<FilterBar {...props} />)
    const input = screen.getByRole('combobox', { name: 'Genre' })
    fireEvent.focus(input)
    fireEvent.click(screen.getByRole('option', { name: 'jazz' }))
    expect(replace).toHaveBeenLastCalledWith('/?genre=jazz', { scroll: false })
  })

  it('shows the active genre from the URL', () => {
    params = new URLSearchParams('genre=punk')
    render(<FilterBar {...props} />)
    expect(screen.getByRole('combobox', { name: 'Genre' })).toHaveValue('punk')
  })
})

describe('FilterBar clear filters', () => {
  beforeEach(() => { params = new URLSearchParams(); replace.mockClear() })

  it('resets every filter, including the genre combobox', () => {
    params = new URLSearchParams('genre=punk&region=sf&q=rose&free=1')
    const { rerender } = render(<FilterBar {...props} />)
    expect(screen.getByRole('combobox', { name: 'Genre' })).toHaveValue('punk')

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(replace).toHaveBeenLastCalledWith('/', { scroll: false })

    // The router then clears the URL; every control follows it.
    params = new URLSearchParams()
    rerender(<FilterBar {...props} />)
    expect(screen.getByRole('combobox', { name: 'Genre' })).toHaveValue('')
    expect(screen.getByLabelText('Search')).toHaveValue('')
    expect(screen.getByLabelText(/free only/i)).not.toBeChecked()
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
  })
})

describe('FilterBar search', () => {
  beforeEach(() => { params = new URLSearchParams(); replace.mockClear(); vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('applies the typed text to the URL as q', () => {
    render(<FilterBar {...props} />)
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'chapel' } })
    act(() => { vi.advanceTimersByTime(300) })
    expect(replace).toHaveBeenLastCalledWith('/?q=chapel', { scroll: false })
  })

  it('carries old band= and venue= links into the box and over to q', () => {
    params = new URLSearchParams('band=rose&venue=chapel&region=sf')
    render(<FilterBar {...props} />)
    expect(screen.getByLabelText('Search')).toHaveValue('rose chapel')
    act(() => { vi.advanceTimersByTime(300) })
    expect(replace).toHaveBeenLastCalledWith('/?region=sf&q=rose+chapel', { scroll: false })
  })
})
