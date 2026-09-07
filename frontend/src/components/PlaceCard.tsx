import type { Place } from '../types'

export function PlaceCard({ place }: { place: Place }) {
  return (
    <div className="place-card">
      <div className="name">{place.name}</div>
      <div className="meta">
        <span className="category-chip">{place.category}</span>
        <span className="distance-eta">
          {place.eta ? `${place.distance} · ${place.eta}` : place.distance}
        </span>
      </div>
      <div className="links">
        <a href={place.maps_url} target="_blank" rel="noopener noreferrer">
          🗺️ Navigate
        </a>
        {place.instagram_url && (
          <a href={place.instagram_url} target="_blank" rel="noopener noreferrer">
            📱 Instagram
          </a>
        )}
      </div>
    </div>
  )
}
