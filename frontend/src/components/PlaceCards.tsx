import type { Place } from '../types'
import { PlaceCard } from './PlaceCard'
import { ShareButton } from './ShareButton'

export function PlaceCards({ places }: { places: Place[] }) {
  return (
    <div className="places">
      {places.map((place) => (
        <PlaceCard key={`${place.name}-${place.maps_url}`} place={place} />
      ))}
      <ShareButton places={places} />
    </div>
  )
}
