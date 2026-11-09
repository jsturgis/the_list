// @vitest-environment node
import { readdirSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { guideHtml, guides, guideSource } from '@/lib/docs'

describe('the guides', () => {
  it('has one per Markdown file in docs/guide/, in their order', () => {
    const files = readdirSync('../docs/guide').filter(f => f.endsWith('.md')).map(f => f.replace(/\.md$/, ''))
    expect(guides.map(g => g.slug).sort()).toEqual(files.sort())
    expect(guides.map(g => g.order)).toEqual([...guides.map(g => g.order)].sort((a, b) => a - b))
    expect(guides[0].slug).toBe('overview')
  })

  it('gives every guide a title, a description and a body', () => {
    for (const guide of guides) {
      expect(guide.title, guide.slug).toBeTruthy()
      expect(guide.description, guide.slug).toBeTruthy()
      expect(guide.html, guide.slug).toMatch(/<(p|h2|ul|pre)\b/)
    }
  })

  it('only links to guides that exist', () => {
    const slugs = new Set(guides.map(g => g.slug))
    for (const guide of guides) {
      for (const [, slug] of guide.html.matchAll(/href="\.\.\/([a-z0-9-]+)\//g)) expect(slugs, `${guide.slug} → ${slug}`).toContain(slug)
      expect(guide.html, guide.slug).not.toMatch(/href="[^":]*\.md\b/)  // a link to a file the site doesn't have
    }
  })

  it("points each guide's edit link at its file on GitHub", () => {
    expect(guideSource('deployment')).toBe('https://github.com/jsturgis/the_list/blob/main/docs/guide/deployment.md')
  })
})

describe('guideHtml', () => {
  it("turns links to other guides' files into links to their pages, keeping the heading", () => {
    expect(guideHtml('<a href="deployment.md">Deployment</a>')).toBe('<a href="../deployment/">Deployment</a>')
    expect(guideHtml('<a href="./alerts.md#dry-run">x</a>')).toBe('<a href="../alerts/#dry-run">x</a>')
  })

  it('leaves other links alone', () => {
    const html = '<a href="https://github.com/jsturgis/the_list/blob/main/DESIGN.md">x</a><a href="#stack">y</a>'
    expect(guideHtml(html)).toBe(html)
  })

  it('makes code blocks and tables, which can scroll sideways, reachable from the keyboard', () => {
    expect(guideHtml('<pre><code>x</code></pre>')).toBe('<pre tabindex="0"><code>x</code></pre>')
    expect(guideHtml('<table><tr><td>x</td></tr></table>')).toBe(
      '<div class="docs-scroll" tabindex="0" role="region" aria-label="Table"><table><tr><td>x</td></tr></table></div>')
  })
})
