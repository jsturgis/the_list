/**
 * A detail page's static paths (getStaticPaths): one at each slug, and one at each id (/bands/12/), where the page
 * redirects to the slug.
 */
export function slugAndIdPaths(ids: string[], slugOf: (id: number) => string): { params: { slug: string } }[] {
  return ids.flatMap(id => [{ params: { slug: slugOf(Number(id)) } }, { params: { slug: id } }])
}
