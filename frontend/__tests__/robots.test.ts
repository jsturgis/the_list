import { describe, it, expect, vi, afterEach } from 'vitest'
import type { APIContext } from 'astro'
import { GET } from '@/pages/robots.txt'

const robots = async (site: string) => (await GET({ site: new URL(site) } as APIContext)).text()

describe('robots.txt', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('allows every crawler and points to the sitemap at the custom domain', async () => {
    vi.stubEnv('BASE_URL', '/')
    const text = await robots('https://list.sturgis.me')
    expect(text).toContain('User-agent: *\nAllow: /')
    expect(text).toContain('Sitemap: https://list.sturgis.me/sitemap-index.xml')
  })

  it('points to the sitemap under the base path', async () => {
    vi.stubEnv('BASE_URL', '/the_list/')
    expect(await robots('https://jsturgis.github.io/the_list')).toContain(
      'Sitemap: https://jsturgis.github.io/the_list/sitemap-index.xml',
    )
  })
})
