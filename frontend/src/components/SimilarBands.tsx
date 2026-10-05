import type { Band } from '@/lib/types'
import BandLink from './BandLink'

interface SimilarBandsProps {
  /** Precomputed in the export; never includes the Band itself. */
  bands: Band[]
}

export default function SimilarBands({ bands }: SimilarBandsProps) {
  if (bands.length === 0) return null

  return (
    <section data-testid="similar-bands">
      <h2 className="text-base font-semibold mb-3 text-ink">
        Similar Bands
      </h2>
      <ul className="flex flex-col gap-1">
        {bands.map(b => (
          <li key={b.id}>
            <BandLink
              bandId={b.id}
              className="flex items-center gap-2 text-sm hover:bg-muted -mx-2 px-2 py-1 rounded"
            >
              <span className="font-medium text-ink">{b.name}</span>
              {b.genres.length > 0 && (
                <span className="text-ink-muted text-xs">
                  {b.genres.slice(0, 2).join(', ')}
                </span>
              )}
            </BandLink>
          </li>
        ))}
      </ul>
    </section>
  )
}
