import { Share2 } from 'lucide-react'
import type { Place } from '../types'
import { formatShareText, whatsAppShareUrl } from '../share'

/** Prefers the native share sheet (best UX, and includes WhatsApp among the
 * options on mobile where it's installed). Where the Web Share API isn't
 * available (desktop, mostly), falls back to a real <a target="_blank">
 * link rather than an imperative window.open() - a script-triggered
 * window.open() is liable to be blocked as a popup by some browsers, while
 * a genuine anchor click is always treated as trusted navigation. */
export function ShareButton({ places }: { places: Place[] }) {
  const text = formatShareText(places)

  if (typeof navigator.share === 'function') {
    return (
      <button
        type="button"
        className="share-button"
        onClick={() => {
          navigator.share({ text }).catch(() => {
            // AbortError (user cancelled) or any other failure - nothing to
            // do, the native share sheet already handles its own error UI.
          })
        }}
      >
        <Share2 size={14} aria-hidden="true" />
        Share these spots
      </button>
    )
  }

  return (
    <a className="share-button" href={whatsAppShareUrl(text)} target="_blank" rel="noopener noreferrer">
      <Share2 size={14} aria-hidden="true" />
      Share these spots
    </a>
  )
}
