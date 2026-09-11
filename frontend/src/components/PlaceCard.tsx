import { Banknote, Camera, Navigation } from 'lucide-react'
import { t } from '../i18n'
import type { Lang, Place } from '../types'

export function PlaceCard({ place, lang }: { place: Place; lang: Lang }) {
  return (
    <div className="place-card">
      <div className="name">{place.name}</div>
      <div className="meta">
        <span className="category-chip">{place.category}</span>
        {place.price_tier && (
          // A distinct icon (not shared with category/tag chips) so it
          // reads as a different kind of fact at a glance, not another tag.
          <span className="price-chip" title={t(lang, 'priceLabel')}>
            <Banknote size={12} aria-hidden="true" />
            {place.price_tier}
          </span>
        )}
        {place.dietary_tags.map((tag) => (
          <span className="tag-chip" key={tag}>
            {tag}
          </span>
        ))}
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
