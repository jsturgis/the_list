import { afterEach, describe, expect, it, vi } from 'vitest'
import { withBasePath } from '@/lib/basePath'

afterEach(() => vi.unstubAllEnvs())

describe('withBasePath', () => {
  it('prefixes the configured base path', () => {
    vi.stubEnv('NEXT_PUBLIC_BASE_PATH', '/the_list')
    expect(withBasePath('/data/shows.json')).toBe('/the_list/data/shows.json')
  })

  it('leaves the path alone without one', () => {
    vi.stubEnv('NEXT_PUBLIC_BASE_PATH', undefined)
    expect(withBasePath('/bands/10/')).toBe('/bands/10/')
  })
})
