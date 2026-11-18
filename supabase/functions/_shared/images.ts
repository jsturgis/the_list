/**
 * What kind of image a file really is, from its first bytes: the browser's type for an upload is only what the file
 * is named. The admin Edge Function stores a screenshot only when its bytes are one of these, under the type they say.
 */

/** "image/png", "image/jpeg" or "image/webp", or null for anything else. Needs the file's first 12 bytes. */
export function sniffImageType(head: Uint8Array): string | null {
  const starts = (bytes: number[], at = 0) => bytes.every((b, i) => head[at + i] === b)
  if (starts([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return 'image/png'
  if (starts([0xff, 0xd8, 0xff])) return 'image/jpeg'
  if (starts([0x52, 0x49, 0x46, 0x46]) && starts([0x57, 0x45, 0x42, 0x50], 8)) return 'image/webp' // RIFF....WEBP
  return null
}
