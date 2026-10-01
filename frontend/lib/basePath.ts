/**
 * Prefix a site path with the base path the site is served under (/the_list on GitHub Pages).
 * Next's Link and router add it themselves; use this for fetch URLs and history entries.
 */
export function withBasePath(path: string): string {
  return `${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}${path}`
}
