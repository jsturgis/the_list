import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { href } from '@/lib/basePath'
import { replaceQuery, useQuery } from '@/lib/navigation'

afterEach(() => vi.unstubAllEnvs())

function Query() {
  return <p data-testid="query">{useQuery().toString()}</p>
}

describe('replaceQuery', () => {
  it('replaces the query on the current page without adding a history entry', () => {
    window.history.replaceState({ router: 'state' }, '', '/shows/1/?genre=punk')
    const entries = window.history.length

    replaceQuery(new URLSearchParams('region=sf&free=1'))

    expect(window.location.pathname).toBe('/shows/1/')
    expect(window.location.search).toBe('?region=sf&free=1')
    expect(window.history.length).toBe(entries)
    expect(window.history.state).toEqual({ router: 'state' })
  })

  it('drops the ? when the query is empty', () => {
    window.history.replaceState(null, '', '/?genre=punk')
    replaceQuery('')
    expect(window.location.href).toBe(`${window.location.origin}/`)
  })

  it('updates components reading useQuery', () => {
    render(<Query />)
    expect(screen.getByTestId('query')).toHaveTextContent(/^$/)

    act(() => replaceQuery('genre=punk'))
    expect(screen.getByTestId('query')).toHaveTextContent('genre=punk')
  })
})

describe('useQuery', () => {
  it('reads the query the page was opened with', () => {
    window.history.replaceState(null, '', '/?q=chapel&region=east_bay')
    render(<Query />)
    expect(screen.getByTestId('query')).toHaveTextContent('q=chapel&region=east_bay')
  })

  it('follows Back and Forward', () => {
    render(<Query />)
    act(() => {
      window.history.replaceState(null, '', '/?free=1')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(screen.getByTestId('query')).toHaveTextContent('free=1')
  })
})

describe('href', () => {
  it('prefixes the configured base path', () => {
    vi.stubEnv('BASE_URL', '/the_list/')
    expect(href('/home-shows.json')).toBe('/the_list/home-shows.json')
    expect(href('/')).toBe('/the_list/')
  })

  it('leaves the path alone without one', () => {
    vi.stubEnv('BASE_URL', '/')
    expect(href('/bands/10/')).toBe('/bands/10/')
  })
})
