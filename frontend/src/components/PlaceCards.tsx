import { ChevronDown } from 'lucide-react'
import type { Place } from '../types'
import { PlaceCard } from './PlaceCard'
import { ShareButton } from './ShareButton'

interface PlaceCardsProps {
  places: Place[]
  hasMore: boolean
  isLoadingMore: boolean
  onShowMore: () => void
}

export function PlaceCards({ places, hasMore, isLoadingMore, onShowMore }: PlaceCardsProps) {
  return (
    <div className="places">
      {places.map((place) => (
        <PlaceCard key={`${place.name}-${place.maps_url}`} place={place} />
      ))}
      {hasMore && (
        <button type="button" className="show-more-button" onClick={onShowMore} disabled={isLoadingMore}>
          <ChevronDown size={15} aria-hidden="true" />
          {isLoadingMore ? 'Loading...' : 'Show more'}
        </button>
      )}
      <ShareButton places={places} />
    </div>
  )
}
