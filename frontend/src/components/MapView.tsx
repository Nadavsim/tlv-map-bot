import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useMemo } from 'react'
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import { t } from '../i18n'
import type { Coordinates, Lang, Place } from '../types'

// Plain OSM tile server, no API key. {s} subdomains (a/b/c) are deprecated by
// OSM, so there's exactly one host - which is also exactly what the backend's
// CSP img-src allows. Change one, change the other.
const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

// divIcons (styled in App.css from the theme tokens) instead of Leaflet's
// default image marker: that one's PNG paths break under Vite bundling, and
// a number needs to be drawn on each pin anyway.
function pinIcon(label: string, className: string): L.DivIcon {
  return L.divIcon({
    className: 'map-pin-wrapper',
    html: `<div class="map-pin ${className}">${label}</div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -16],
  })
}

// Refits whenever the pin set changes - which is what makes "Show more"
// results appear in view instead of landing off-screen.
function FitBounds({ origin, places }: { origin: Coordinates; places: Place[] }) {
  const map = useMap()
  useEffect(() => {
    const points: L.LatLngTuple[] = [[origin.lat, origin.lon], ...places.map((p): L.LatLngTuple => [p.lat, p.lon])]
    map.fitBounds(L.latLngBounds(points), { padding: [36, 36], maxZoom: 17 })
  }, [map, origin, places])
  return null
}

// Selecting a card from the list should bring its pin into view if the user
// has panned/zoomed away - but never fight them when it's already visible.
function PanToActive({ place }: { place: Place | null }) {
  const map = useMap()
  useEffect(() => {
    if (!place) return
    const latlng = L.latLng(place.lat, place.lon)
    if (!map.getBounds().contains(latlng)) map.panTo(latlng)
  }, [map, place])
  return null
}

interface MapViewProps {
  origin: Coordinates
  places: Place[]
  activeIndex: number | null
  onSelect: (index: number) => void
  lang: Lang
}

// Default export: this module is only ever loaded through React.lazy, so
// Leaflet and its CSS stay out of the initial bundle.
export default function MapView({ origin, places, activeIndex, onSelect, lang }: MapViewProps) {
  const originIcon = useMemo(() => pinIcon('', 'map-pin-origin'), [])
  const activePlace = activeIndex !== null ? (places[activeIndex] ?? null) : null

  return (
    <div className="map-view" role="region" aria-label={t(lang, 'mapLabel')}>
      <MapContainer
        center={[origin.lat, origin.lon]}
        zoom={15}
        // The map sits inside a scrolling chat log: a wheel/one-finger drag
        // that zooms/pans the map instead of scrolling the page is a trap.
        // Desktop: wheel scrolls the page, zoom via buttons. Touch: one-finger
        // drag scrolls the page, pinch (which also pans) still works.
        scrollWheelZoom={false}
        dragging={!L.Browser.mobile}
      >
        <TileLayer url={TILE_URL} attribution={ATTRIBUTION} maxZoom={19} />
        <Marker position={[origin.lat, origin.lon]} icon={originIcon} zIndexOffset={1000}>
          <Popup>{t(lang, 'mapYouAreHere')}</Popup>
        </Marker>
        {places.map((place, i) => (
          <Marker
            key={`${place.name}-${place.maps_url}`}
            position={[place.lat, place.lon]}
            icon={pinIcon(String(i + 1), i === activeIndex ? 'map-pin-active' : '')}
            zIndexOffset={i === activeIndex ? 500 : 0}
            eventHandlers={{ click: () => onSelect(i) }}
          >
            {/* dir="auto": the map container is pinned to ltr (Leaflet's own
                absolute positioning breaks under rtl), so a Hebrew name
                decides its own direction here instead. */}
            <Popup>
              <span dir="auto">{place.name}</span>
            </Popup>
          </Marker>
        ))}
        <FitBounds origin={origin} places={places} />
        <PanToActive place={activePlace} />
      </MapContainer>
    </div>
  )
}
