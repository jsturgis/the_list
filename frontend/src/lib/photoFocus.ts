import type { ImageFocus } from './types'

/**
 * Where a photo without a focal point is anchored when it's cropped: centred across, a little above the middle, since
 * heads tend to be in the top part of a photo. The backend gives a stored photo with no face the same point
 * (backend/app/ingestion/photo_focus.py).
 */
export const DEFAULT_PHOTO_FOCUS: ImageFocus = { x: 50, y: 35 }

/** The CSS object-position for a cropped (`object-cover`) photo: its focal point, else the default. */
export function objectPosition(focus?: ImageFocus | null): string {
  const { x, y } = focus ?? DEFAULT_PHOTO_FOCUS
  return `${x}% ${y}%`
}
