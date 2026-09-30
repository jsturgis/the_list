import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
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
