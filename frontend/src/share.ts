import { t } from './i18n'
import type { Lang, Place } from './types'

// The shared text previously had no link back to the app at all - a
// recipient got restaurant info but no way to try the bot themselves,
// which is the whole point of sharing being a growth mechanic rather than
// just a convenience. `src=share` marks a visitor as having arrived via a
// shared link, read once on load to time the PWA install prompt.
function shareAppUrl(): string {
  return `${window.location.origin}/?src=share`
}

export function formatShareText(places: Place[], lang: Lang): string {
  const entries = places.map((place, i) => {
    const distanceEta = place.eta ? `${place.distance} - ${place.eta}` : place.distance
    const lines = [`${i + 1}. ${place.name} (${place.category})`, `📍 ${distanceEta}`, `🗺️ ${place.maps_url}`]
    if (place.instagram_url) {
      lines.push(`📸 ${place.instagram_url}`)
    }
    return lines.join('\n')
  })

  const footer = `🤝 ${t(lang, 'shareFooterPitch')}\n${t(lang, 'shareFooterCta')} ${shareAppUrl()}`
  return `🍽️ ${t(lang, 'shareHeader')}\n\n${entries.join('\n\n')}\n\n${footer}`
}

export function whatsAppShareUrl(text: string): string {
  return `https://wa.me/?text=${encodeURIComponent(text)}`
}
