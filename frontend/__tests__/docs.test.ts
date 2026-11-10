// @vitest-environment node
import { readdirSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { guideHtml, guides, guideSource, hasDiagram } from '@/lib/docs'

describe('the guides', () => {
  it('has one per Markdown file in docs/guide/, in their order', () => {
    const files = readdirSync('../docs/guide').filter(f => f.endsWith('.md')).map(f => f.replace(/\.md$/, ''))
    expect(guides.map(g => g.slug).sort()).toEqual(files.sort())
    expect(guides.map(g => g.order)).toEqual([...guides.map(g => g.order)].sort((a, b) => a - b))
    expect(guides[0].slug).toBe('overview')
    expect(guides[1].slug).toBe('architecture')
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

  it('names every diagram after its accTitle', () => {
    const names = guides.flatMap(guide =>
      [...guide.html.matchAll(/<div class="docs-diagram" data-diagram [^>]*aria-label="([^"]*)"/g)].map(([, name]) => name))
    expect(names.length).toBeGreaterThanOrEqual(6)
    for (const name of names) expect(name).toMatch(/^Diagram: \S/)
    const architecture = guides.find(g => g.slug === 'architecture')!
    expect(hasDiagram(architecture.html)).toBe(true)
    expect(architecture.html).not.toContain('language-mermaid')
    expect(hasDiagram(guides.find(g => g.slug === 'local-setup')!.html)).toBe(false)
  })

  it("only links to headings that exist, in its own guide or another's", () => {
    const html = new Map(guides.map(g => [g.slug, g.html]))
    for (const guide of guides) {
      for (const [, slug, id] of guide.html.matchAll(/href="(?:\.\.\/([a-z0-9-]+)\/)?#([^"]+)"/g)) {
        expect(html.get(slug ?? guide.slug), `${guide.slug} → ${slug ?? guide.slug}#${id}`).toContain(`id="${id}"`)
      }
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

  it('turns a mermaid block into a focusable region named after its accTitle, holding its source', () => {
    const source = 'flowchart TD\n  accTitle: The weekly run\n  a["x &amp; y"] --&gt; b\n'
    const html = guideHtml(`<pre><code class="language-mermaid">${source}</code></pre>`)
    expect(html).toBe(
      '<div class="docs-diagram" data-diagram tabindex="0" role="region" aria-label="Diagram: The weekly run">' +
      `<pre><code>${source}</code></pre></div>`)
    expect(hasDiagram(html)).toBe(true)
  })

  it('escapes quotes in the name, and names a diagram without an accTitle plainly', () => {
    expect(guideHtml('<pre><code class="language-mermaid">erDiagram\n  accTitle: Say "hi"\n</code></pre>'))
      .toContain('aria-label="Diagram: Say &quot;hi&quot;"')
    expect(guideHtml('<pre><code class="language-mermaid">flowchart LR\n  a --&gt; b\n</code></pre>'))
      .toContain('aria-label="Diagram"')
  })

  it('draws each of several diagrams, and leaves other code blocks as code blocks', () => {
    const html = guideHtml(
      '<pre><code class="language-mermaid">flowchart LR\n</code></pre>' +
      '<pre><code class="language-bash">npm test\n</code></pre>' +
      '<pre><code class="language-mermaid">erDiagram\n</code></pre>')
    expect(html.match(/data-diagram/g)).toHaveLength(2)
    expect(html).toContain('<pre tabindex="0"><code class="language-bash">npm test\n</code></pre>')
    expect(hasDiagram(guideHtml('<pre><code>accTitle: x</code></pre>'))).toBe(false)
  })
})
