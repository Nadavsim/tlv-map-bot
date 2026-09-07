import { ChevronDown } from 'lucide-react'
import { t } from '../i18n'
import type { Lang, Place } from '../types'
import { PlaceCard } from './PlaceCard'
import { ShareButton } from './ShareButton'

interface PlaceCardsProps {
  places: Place[]
  hasMore: boolean
  isLoadingMore: boolean
  onShowMore: () => void
  lang: Lang
}

export function PlaceCards({ places, hasMore, isLoadingMore, onShowMore, lang }: PlaceCardsProps) {
  return (
    <div className="places">
      {places.map((place) => (
        <PlaceCard key={`${place.name}-${place.maps_url}`} place={place} lang={lang} />
      ))}
      {hasMore && (
        <button type="button" className="show-more-button" onClick={onShowMore} disabled={isLoadingMore}>
          <ChevronDown size={15} aria-hidden="true" />
          {isLoadingMore ? t(lang, 'showMoreLoading') : t(lang, 'showMore')}
        </button>
      )}
      <ShareButton places={places} lang={lang} />
    </div>
  )
}
