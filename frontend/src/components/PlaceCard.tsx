import { Camera, Navigation } from 'lucide-react'
import { t } from '../i18n'
import type { Lang, Place } from '../types'

export function PlaceCard({ place, lang }: { place: Place; lang: Lang }) {
  return (
    <div className="place-card">
      <div className="name" dir="auto">
        {place.name}
      </div>
      <div className="meta">
        <span className="category-chip">{place.category}</span>
        {place.dietary_tags.map((tag) => (
          <span className="tag-chip" key={tag}>
            {tag}
          </span>
        ))}
        <span className="distance-eta">
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
