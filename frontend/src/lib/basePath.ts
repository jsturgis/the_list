/** A site path under the base path the site is served from (/the_list on GitHub Pages), for links, fetches and history entries. */
export function href(path: string): string {
  // BASE_URL ends in a slash ("/the_list/", or "/" with the custom domain); paths start with one.
  return `${import.meta.env.BASE_URL.replace(/\/$/, '')}${path}`
}
