/**
 * The guides on the docs pages (/docs/): the Markdown files in the repository's docs/guide/, rendered at build time.
 * Each starts with a title, a one-line description and its place in the list (`order`).
 */
import type { MarkdownInstance } from 'astro'

interface Frontmatter {
  title: string
  description: string
  order: number
}

export interface Guide extends Frontmatter {
  /** Its file name without `.md`, and its page's URL: /docs/<slug>/. */
  slug: string
  /** Its body as HTML, ready for the page (guideHtml). */
  html: string
}

/** Where a guide's source is on GitHub, for its "Edit on GitHub" link. */
export const guideSource = (slug: string) => `https://github.com/jsturgis/the_list/blob/main/docs/guide/${slug}.md`

/**
 * A guide's rendered Markdown, made ready for its page. The files are also read on GitHub, so they link to each other
 * by file name ("deployment.md#rolling-back"): those links go to the guide's page instead ("../deployment/#rolling-back").
 * Code blocks and tables can scroll sideways on phones, and a scrolling region must take keyboard focus, so code
 * blocks get a tabindex and tables a focusable wrapper.
 */
export function guideHtml(html: string): string {
  return html
    .replace(/href="(?:\.\/)?([a-z0-9-]+)\.md(#[^"]*)?"/g, (_, slug: string, hash = '') => `href="../${slug}/${hash}"`)
    .replace(/<pre(?=[\s>])/g, '<pre tabindex="0"')
    .replace(/<table(?=[\s>])/g, '<div class="docs-scroll" tabindex="0" role="region" aria-label="Table"><table')
    .replace(/<\/table>/g, '</table></div>')
}

const files = import.meta.glob<MarkdownInstance<Frontmatter>>('../../../docs/guide/*.md', { eager: true })

/** Every guide, in their `order`. */
export const guides: Guide[] = (await Promise.all(Object.entries(files).map(async ([path, md]) => ({
  slug: path.split('/').pop()!.replace(/\.md$/, ''),
  ...md.frontmatter,
  html: guideHtml(await md.compiledContent()),
})))).sort((a, b) => a.order - b.order)
