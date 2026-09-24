import { Banknote, Camera, Clock, Navigation, Umbrella } from 'lucide-react'
import { t } from '../i18n'
import type { Lang, Place } from '../types'

// "23" -> "23:00" - the raw hour this app stores/sends, formatted the one
// way a chip actually needs to show it.
function formatClosesAt(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`
}

export function PlaceCard({ place, lang }: { place: Place; lang: Lang }) {
  return (
    <div className="place-card">
      <div className="name">{place.name}</div>
      <div className="meta">
        <span className="category-chip">{place.category}</span>
        {place.price_tier && (
          // A distinct icon (not shared with category/tag chips) so it
          // reads as a different kind of fact at a glance, not another tag.
          // aria-label (not just title, which never fires on touch) gives
          // screen readers a real accessible name instead of reading the
          // bare "$" characters as unexplained punctuation. dir="ltr"
          // mirrors .distance-eta just below - today's $/$$/$$$ glyphs are
          // palindromic so it's not visibly broken without this, but it's
          // the same class of RTL-in-a-bidi-document content that caused
          // this project's first-ever RTL bug.
          <span
            className="price-chip"
            title={t(lang, 'priceLabel')}
            aria-label={`${t(lang, 'priceLabel')}: ${place.price_tier}`}
            dir="ltr"
          >
            <Banknote size={12} aria-hidden="true" />
            {place.price_tier}
          </span>
        )}
        {place.dietary_tags.map((tag) => (
          <span className="tag-chip" key={tag}>
            {tag}
          </span>
        ))}
        {place.closes_at_hour !== null && (
          <span
            className="hours-chip"
            title={t(lang, 'closesAtLabel')}
            aria-label={`${t(lang, 'closesAtLabel')}: ${formatClosesAt(place.closes_at_hour)}`}
            dir="ltr"
          >
            <Clock size={12} aria-hidden="true" />
            {formatClosesAt(place.closes_at_hour)}
          </span>
        )}
        {place.outdoor_seating && (
          <span className="outdoor-chip" title={t(lang, 'outdoorSeatingLabel')}>
            <Umbrella size={12} aria-hidden="true" />
            {t(lang, 'outdoorSeatingLabel')}
          </span>
        )}
        <span className="distance-eta" dir="ltr">
          {place.eta ? `${place.distance} · ${place.eta}` : place.distance}
        </span>
      </div>
      <div className="links">
        <a href={place.maps_url} target="_blank" rel="noopener noreferrer">
          <Navigation size={14} aria-hidden="true" />
          {t(lang, 'navigate')}
        </a>
        {place.instagram_url && (
          <a href={place.instagram_url} target="_blank" rel="noopener noreferrer">
            <Camera size={14} aria-hidden="true" />
            {t(lang, 'instagram')}
          </a>
        )}
      </div>
    </div>
  )
}
