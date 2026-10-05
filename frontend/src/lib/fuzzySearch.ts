/**
 * The home page's "band or venue" search. Mirrors the backend's `app/fuzzy_search.py` exactly, so
 * browser filtering and the API's `search` filter agree; change both together.
 */

/** Lowercase, strip accents, and turn every run of non-alphanumerics into one space. */
export function normalize(s: string): string {
  return s
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
}

/**
 * Smallest edit distance (Damerau/OSA: a swap of adjacent letters is one edit) between `token` and
 * any prefix of `word`, so a partly typed word still counts.
 */
export function fuzzyPrefixDistance(token: string, word: string): number {
  const m = token.length, n = word.length
  // d[i][j]: distance between token[:i] and word[:j].
  const d: number[][] = Array.from({ length: m + 1 }, (_, i) => [i, ...Array<number>(n).fill(0)])
  for (let j = 1; j <= n; j++) d[0][j] = j
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = token[i - 1] === word[j - 1] ? 0 : 1
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
      if (i > 1 && j > 1 && token[i - 1] === word[j - 2] && token[i - 2] === word[j - 1]) {
        d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1)
      }
    }
  }
  return Math.min(...d[m])
}

/**
 * Typos allowed for a token: none under 5 characters, 1 up to 8, then 2. Shorter tokens with a
 * typo match far too much (e.g. "rose" would match "Roberts").
 */
function allowedTypos(token: string): number {
  if (token.length < 5) return 0
  return token.length < 9 ? 1 : 2
}

/** Whether one normalized query token matches a name: a substring, or a near-miss prefix of one of its words. */
export function tokenMatches(token: string, name: string): boolean {
  const n = normalize(name)
  if (n.includes(token)) return true
  const k = allowedTypos(token)
  return k > 0 && n.split(' ').some(word => fuzzyPrefixDistance(token, word) <= k)
}

/** Whether every word of `query` matches at least one of `names` (words may match different names). */
export function matchesSearch(query: string, names: string[]): boolean {
  const tokens = normalize(query).split(' ').filter(Boolean)
  return tokens.every(token => names.some(name => tokenMatches(token, name)))
}
