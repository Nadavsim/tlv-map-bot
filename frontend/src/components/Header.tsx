import { Car, Footprints, MapPin } from 'lucide-react'
import type { TransportMode } from '../types'

interface HeaderProps {
  locationStatus: string
  mode: TransportMode
  onModeChange: (mode: TransportMode) => void
}

export function Header({ locationStatus, mode, onModeChange }: HeaderProps) {
  return (
    <header>
      <h1>
        <MapPin size={22} strokeWidth={2.5} aria-hidden="true" />
        TLV Bot
      </h1>
      <p className="location-status">{locationStatus}</p>
      <div className="mode-toggle" role="group" aria-label="Transport mode">
        <button
          type="button"
          className={mode === 'walking' ? 'active' : ''}
          onClick={() => onModeChange('walking')}
        >
          <Footprints size={16} aria-hidden="true" />
          Walk
        </button>
        <button
          type="button"
          className={mode === 'driving' ? 'active' : ''}
          onClick={() => onModeChange('driving')}
        >
          <Car size={16} aria-hidden="true" />
          Drive
        </button>
      </div>
    </header>
  )
}
