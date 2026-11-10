import { defineCollection } from 'astro:content'
import { glob } from 'astro/loaders'
import { docsSchema } from '@astrojs/starlight/schema'

/**
 * The docs (Starlight): the Markdown guides in the repository's docs/guide/, which GitHub shows as they are. Each
 * guide's page is at /docs/<file name>/, and index.md is the docs' home page, /docs/.
 */
export const collections = {
  docs: defineCollection({
    loader: glob({
      pattern: '*.md',
      base: '../docs/guide',
      generateId: ({ entry }) => guideId(entry),
    }),
    schema: docsSchema(),
  }),
}

/** A guide's id, which is also its URL path: "docs" for index.md, "docs/local-setup" for local-setup.md. */
export function guideId(file: string): string {
  const name = file.replace(/\.md$/, '')
  return name === 'index' ? 'docs' : `docs/${name}`
}
