// @vitest-environment node
import { experimental_AstroContainer as AstroContainer } from 'astro/container'
import { getContainerRenderer } from '@astrojs/react/container-renderer'
import { loadRenderers } from 'astro:container'
import { beforeAll, describe, expect, it } from 'vitest'
import NotFoundPage from '@/pages/404.astro'
import AlertsPage from '@/pages/alerts/index.astro'
import UnsubscribePage from '@/pages/alerts/unsubscribe.astro'

let container: AstroContainer

beforeAll(async () => {
  container = await AstroContainer.create({ renderers: await loadRenderers([getContainerRenderer()]) })
})

const render = (page: Parameters<AstroContainer['renderToString']>[0]) => container.renderToString(page)

describe('the 404 page', () => {
  it('says the page is missing and links to the Shows list', async () => {
    const html = await render(NotFoundPage)
    expect(html).toMatch(/<h1[^>]*>Page not found<\/h1>/)
    expect(html).toMatch(/<a href="\/"[^>]*>See this week(&#39;|&apos;|')s shows<\/a>/)
    expect(html).toContain('<title>The List — SF Bay Area Music</title>')
  })
})

describe('page metadata', () => {
  it('gives the Alerts page its own title and description, indexable', async () => {
    const html = await render(AlertsPage)
    expect(html).toContain('<title>Your alerts — The List</title>')
    expect(html).toContain('content="Saved searches and the weekly email of matching SF Bay Area shows."')
    expect(html).not.toContain('noindex')
  })

  it('keeps the Unsubscribe page out of search indexes', async () => {
    const html = await render(UnsubscribePage)
    expect(html).toContain('<title>Unsubscribe — The List</title>')
    expect(html).toContain('<meta name="robots" content="noindex">')
  })
})
