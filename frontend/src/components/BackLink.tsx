import { ArrowLeftIcon } from '@heroicons/react/20/solid'
import { href } from '@/lib/basePath'

/**
 * Goes back in history; when there's nothing on this site to go back to (page opened directly or from another
 * site), goes to the Shows list, keeping any filters in the URL. Both are done in the browser by lib/keepFilters.
 */
export default function BackLink() {
  return (
    <a
      href={href('/')}
      data-keep-filters=""
      data-back=""
      className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink-soft"
    >
      <ArrowLeftIcon className="size-4 shrink-0" />
      Back
    </a>
  )
}
