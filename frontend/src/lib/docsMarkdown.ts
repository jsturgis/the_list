/**
 * A remark plugin for the docs (Starlight), which render the Markdown guides in the repository's docs/guide/.
 *
 * The same files are read on GitHub, so they link to each other by file name ("deployment.md#rolling-back") and
 * hold their diagrams as ```mermaid blocks, which GitHub draws. On the site:
 *  - a link to another guide's file goes to that guide's page ("../deployment/#rolling-back");
 *  - a ```mermaid block becomes a focusable region named after its `accTitle`, holding its source. The page's
 *    script draws the diagram there (lib/diagrams); without JavaScript the source shows.
 */

/** The guides in the docs' sidebar, in order: their file names in docs/guide/, without ".md". A test checks none is left out. */
export const GUIDES = ['overview', 'architecture', 'local-setup', 'configuration', 'ingestion', 'deployment', 'alerts', 'project-structure']

interface MdNode {
  type: string
  url?: string
  lang?: string | null
  value?: string
  children?: MdNode[]
}

const escapeHtml = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

/**
 * A link to a guide by its file name, as a link to its page. Pages are directories (/docs/deployment/), so from a
 * guide's page another guide is "../<name>/"; from the docs' home page (index.md) it's "./<name>/".
 */
export function guideHref(href: string, fromIndex = false): string {
  const match = href.match(/^(?:\.\/)?([a-z0-9-]+)\.md(#.*)?$/)
  if (!match) return href
  const [, name, hash = ''] = match
  const up = fromIndex ? './' : '../'
  return name === 'index' ? `${up}${hash}` : `${up}${name}/${hash}`
}

/** The HTML that stands in for a ```mermaid block until lib/diagrams draws it. */
export function diagramHtml(source: string): string {
  const title = /^[ \t]*accTitle:[ \t]*(.+)$/m.exec(source)?.[1].trim()
  const name = escapeHtml(title ? `Diagram: ${title}` : 'Diagram').replace(/"/g, '&quot;')
  // not-content: Starlight's Markdown styles leave it alone.
  return `<div class="docs-diagram not-content" data-diagram tabindex="0" role="region" aria-label="${name}">` +
    `<pre>${escapeHtml(source)}</pre></div>`
}

function walk(node: MdNode, fromIndex: boolean): void {
  for (const child of node.children ?? []) {
    if (child.type === 'link' && child.url) child.url = guideHref(child.url, fromIndex)
    if (child.type === 'code' && child.lang === 'mermaid') {
      child.type = 'html'
      child.value = diagramHtml(child.value ?? '')
      delete child.lang
    }
    walk(child, fromIndex)
  }
}

export default function remarkDocs() {
  return (tree: MdNode, file: { path?: string; history?: string[] }) => {
    const path = file.path ?? file.history?.[0] ?? ''
    // Only the guides: other Markdown has no such links or diagrams.
    if (!/[\\/]docs[\\/]guide[\\/][^\\/]+\.md$/.test(path)) return
    walk(tree, /[\\/]index\.md$/.test(path))
  }
}
