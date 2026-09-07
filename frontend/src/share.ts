import { t } from './i18n'
import type { Lang, Place } from './types'

export function formatShareText(places: Place[], lang: Lang): string {
  const entries = places.map((place, i) => {
    const distanceEta = place.eta ? `${place.distance} - ${place.eta}` : place.distance
    const lines = [`${i + 1}. ${place.name} (${place.category})`, `📍 ${distanceEta}`, `🗺️ ${place.maps_url}`]
    if (place.instagram_url) {
      lines.push(`📸 ${place.instagram_url}`)
    }
    return lines.join('\n')
  })

  return `🍽️ ${t(lang, 'shareHeader')}\n\n${entries.join('\n\n')}`
}

export function whatsAppShareUrl(text: string): string {
  return `https://wa.me/?text=${encodeURIComponent(text)}`
}
