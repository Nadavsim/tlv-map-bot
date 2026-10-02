import { ChevronDown, Map as MapIcon } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { t } from '../i18n'
import type { Coordinates, Lang, Place } from '../types'
import { MapErrorBoundary } from './MapErrorBoundary'
import { PlaceCard } from './PlaceCard'
import { ShareButton } from './ShareButton'

// Leaflet (~150KB) is only fetched the first time someone opens a map - the
// chat itself never pays for it.
const MapView = lazy(() => import('./MapView'))

interface PlaceCardsProps {
  places: Place[]
  origin: Coordinates
  hasMore: boolean
  isLoadingMore: boolean
  onShowMore: () => void
  lang: Lang
}

export function PlaceCards({ places, origin, hasMore, isLoadingMore, onShowMore, lang }: PlaceCardsProps) {
  // Local to this results block (not App state): each results entry has its
  // own map, and nothing outside it needs to know whether it's open.
  const [mapOpen, setMapOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const cardRefs = useRef<(HTMLDivElement | null)[]>([])
  const mapRef = useRef<HTMLDivElement>(null)

  // Bring the map into view when it opens - it renders below the cards, and
  // the toggle that opened it can be a screen away from where it lands.
  useEffect(() => {
    if (mapOpen) mapRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [mapOpen])

  // Pin tapped -> its card scrolls into view. Card selected -> the map
  // highlights the pin (no scroll: the card is what was just tapped).
  function handlePinSelect(index: number) {
    setActiveIndex(index)
    cardRefs.current[index]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  return (
    <div className="places">
      {places.map((place, i) => (
        <div key={`${place.name}-${place.maps_url}`} ref={(el) => void (cardRefs.current[i] = el)}>
          <PlaceCard
            place={place}
            lang={lang}
            mapNumber={mapOpen ? i + 1 : undefined}
            isActive={mapOpen && activeIndex === i}
            onSelect={mapOpen ? () => setActiveIndex(i) : undefined}
          />
        </div>
      ))}
      {mapOpen && (
        <div ref={mapRef}>
          <MapErrorBoundary lang={lang}>
            <Suspense fallback={<div className="map-view map-placeholder">{t(lang, 'mapLoading')}</div>}>
              <MapView origin={origin} places={places} activeIndex={activeIndex} onSelect={handlePinSelect} lang={lang} />
            </Suspense>
          </MapErrorBoundary>
        </div>
      )}
      {hasMore && (
        <button type="button" className="show-more-button" onClick={onShowMore} disabled={isLoadingMore}>
          <ChevronDown size={15} aria-hidden="true" />
          {isLoadingMore ? t(lang, 'showMoreLoading') : t(lang, 'showMore')}
        </button>
      )}
      <button
        type="button"
        className="show-more-button"
        aria-expanded={mapOpen}
        onClick={() => {
          setMapOpen((open) => !open)
          setActiveIndex(null)
        }}
      >
        <MapIcon size={15} aria-hidden="true" />
        {mapOpen ? t(lang, 'hideMap') : t(lang, 'showMap')}
      </button>
      <ShareButton places={places} lang={lang} />
    </div>
  )
}
