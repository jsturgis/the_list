/** A site path under the base path the site is served from (/the_list on GitHub Pages), for links, fetches and history entries. */
export function href(path: string): string {
  return `${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}${path}`
}
