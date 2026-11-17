// @vitest-environment node
import { readdirSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import remarkDocs, { diagramHtml, guideHref, GUIDES } from '@/lib/docsMarkdown'
import { guideId } from '@/content.config'

// The docs (Starlight, at /docs/) render the Markdown guides in the repository's docs/guide/. These check the guides
// themselves, as files, and the plugin that adapts them for the site; e2e/docs.spec.ts checks the built pages.

const DIR = '../docs/guide'
const files = readdirSync(DIR).filter(f => f.endsWith('.md')).sort()
const guides = new Map(files.map(f => [f.replace(/\.md$/, ''), readFileSync(`${DIR}/${f}`, 'utf8')]))

/** A heading's id on GitHub and on the site: lowercased, punctuation dropped, spaces as hyphens. */
const headingId = (heading: string) =>
  heading.trim().toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, '').replace(/\s/g, '-')
/** A guide's text outside its code blocks. */
const prose = (text: string) => text.replace(/^```[\s\S]*?^```/gm, '')
const headingIds = (text: string) => new Set([...prose(text).matchAll(/^#{2,6}\s+(.+)$/gm)].map(m => headingId(m[1])))

describe('the guides', () => {
  it("are all in the docs' sidebar, and the sidebar lists nothing else", () => {
    expect([...GUIDES].sort()).toEqual([...guides.keys()].filter(name => name !== 'index').sort())
    expect(GUIDES[0]).toBe('overview')
  })

  it('each have a title and a description', () => {
    for (const [name, text] of guides) {
      const frontmatter = /^---\n([\s\S]*?)\n---\n/.exec(text)?.[1] ?? ''
      expect(frontmatter, name).toMatch(/^title: \S/m)
      expect(frontmatter, name).toMatch(/^description: \S/m)
    }
  })

  it('link to each other by file name, and only to guides and headings that exist', () => {
    let links = 0
    for (const [name, text] of guides) {
      for (const [, file, hash] of prose(text).matchAll(/\]\((?:\.\/)?([a-z0-9-]+\.md)?(?:#([^)\s]+))?\)/g)) {
        if (!file && !hash) continue
        const target = file ? file.replace(/\.md$/, '') : name
        expect([...guides.keys()], `${name} → ${file}`).toContain(target)
        if (hash) expect([...headingIds(guides.get(target)!)], `${name} → ${target}#${hash}`).toContain(hash)
        links++
      }
    }
    expect(links).toBeGreaterThan(20)
  })

  it('the docs home page links to every guide', () => {
    for (const name of GUIDES) expect(guides.get('index')).toContain(`(${name}.md)`)
  })

  it('name every diagram with an accTitle', () => {
    let diagrams = 0
    for (const [name, text] of guides) {
      for (const [, source] of text.matchAll(/^```mermaid\n([\s\S]*?)^```/gm)) {
        expect(source, name).toMatch(/^\s*accTitle: \S/m)
        diagrams++
      }
    }
    expect(diagrams).toBeGreaterThanOrEqual(7)
  })
})

describe('guide URLs', () => {
  it('puts each guide at /docs/<file name>/, and index.md at /docs/', () => {
    expect(guideId('local-setup.md')).toBe('docs/local-setup')
    expect(guideId('index.md')).toBe('docs')
  })
})

describe('guideHref', () => {
  it("turns a link to another guide's file into a link to its page, keeping the heading", () => {
    expect(guideHref('deployment.md')).toBe('../deployment/')
    expect(guideHref('./alerts.md#dry-run')).toBe('../alerts/#dry-run')
  })

  it("links from the docs home page, which is one level up, and back to it", () => {
    expect(guideHref('overview.md', true)).toBe('./overview/')
    expect(guideHref('index.md')).toBe('../')
  })

  it('leaves other links alone', () => {
    for (const href of ['https://github.com/jsturgis/the_list/blob/main/DESIGN.md', '#stack', 'mailto:a@example.com', '../adr/0002.md']) {
      expect(guideHref(href)).toBe(href)
    }
  })
})

describe('diagramHtml', () => {
  it('makes a focusable region named after the accTitle, holding the escaped source', () => {
    const html = diagramHtml('flowchart TD\n  accTitle: The site at build time\n  a["<b>x</b>"] --> b')
    expect(html).toMatch(/^<div class="docs-diagram not-content" data-diagram tabindex="0" role="region" aria-label="Diagram: The site at build time">/)
    expect(html).toContain('<pre>flowchart TD\n  accTitle: The site at build time\n  a["&lt;b&gt;x&lt;/b&gt;"] --&gt; b</pre>')
  })

  it('escapes quotes in the name, and names a diagram without an accTitle plainly', () => {
    expect(diagramHtml('flowchart TD\n  accTitle: The "weekly" run\n  a --> b')).toContain('aria-label="Diagram: The &quot;weekly&quot; run"')
    expect(diagramHtml('flowchart TD\n  a --> b')).toContain('aria-label="Diagram"')
  })
})

describe('the Markdown plugin', () => {
  const tree = () => ({
    type: 'root',
    children: [
      { type: 'paragraph', children: [{ type: 'link', url: 'deployment.md#settings', children: [] }] },
      { type: 'code', lang: 'mermaid', value: 'flowchart TD\n  a --> b' },
      { type: 'code', lang: 'bash', value: 'npm ci' },
    ],
  })

  it('rewrites guide links and turns mermaid blocks into diagram regions, leaving other code alone', () => {
    const root = tree()
    remarkDocs()(root, { path: '/repo/docs/guide/overview.md' })
    expect(root.children[0].children![0].url).toBe('../deployment/#settings')
    expect(root.children[1]).toMatchObject({ type: 'html', value: expect.stringContaining('data-diagram') })
    expect(root.children[2]).toEqual({ type: 'code', lang: 'bash', value: 'npm ci' })
  })

  it('links from index.md one level up', () => {
    const root = tree()
    remarkDocs()(root, { path: '/repo/docs/guide/index.md' })
    expect(root.children[0].children![0].url).toBe('./deployment/#settings')
  })

  it('leaves Markdown outside docs/guide/ alone', () => {
    const root = tree()
    remarkDocs()(root, { path: '/repo/frontend/src/notes.md' })
    expect(root).toEqual(tree())
  })
})
