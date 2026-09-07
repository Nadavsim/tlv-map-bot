import { Car, CircleHelp, Footprints, MapPin } from 'lucide-react'
import type { TransportMode } from '../types'

interface HeaderProps {
  locationStatus: string
  mode: TransportMode
  onModeChange: (mode: TransportMode) => void
  onHelp: () => void
}

export function Header({ locationStatus, mode, onModeChange, onHelp }: HeaderProps) {
  return (
    <header>
      <div className="header-top">
        <h1>
          <MapPin size={22} strokeWidth={2.5} aria-hidden="true" />
          TLV Bot
        </h1>
        <button type="button" className="help-button" onClick={onHelp} aria-label="Help">
          <CircleHelp size={20} aria-hidden="true" />
        </button>
      </div>
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
