import { Share2 } from 'lucide-react'
import { t } from '../i18n'
import { formatShareText, whatsAppShareUrl } from '../share'
import type { Lang, Place } from '../types'

/** Prefers the native share sheet (best UX, and includes WhatsApp among the
 * options on mobile where it's installed). Where the Web Share API isn't
 * available (desktop, mostly), falls back to a real <a target="_blank">
 * link rather than an imperative window.open() - a script-triggered
 * window.open() is liable to be blocked as a popup by some browsers, while
 * a genuine anchor click is always treated as trusted navigation. */
export function ShareButton({ places, lang }: { places: Place[]; lang: Lang }) {
  const text = formatShareText(places, lang)

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
        {t(lang, 'shareSpots')}
      </button>
    )
  }

  return (
    <a className="share-button" href={whatsAppShareUrl(text)} target="_blank" rel="noopener noreferrer">
      <Share2 size={14} aria-hidden="true" />
      {t(lang, 'shareSpots')}
    </a>
  )
}
