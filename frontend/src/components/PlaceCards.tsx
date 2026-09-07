import type { Place } from '../types'
import { PlaceCard } from './PlaceCard'

export function PlaceCards({ places }: { places: Place[] }) {
  return (
    <div className="places">
      {places.map((place) => (
        <PlaceCard key={`${place.name}-${place.maps_url}`} place={place} />
      ))}
    </div>
  )
}
