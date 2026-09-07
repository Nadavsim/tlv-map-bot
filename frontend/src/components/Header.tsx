import type { TransportMode } from '../types'

interface HeaderProps {
  locationStatus: string
  mode: TransportMode
  onModeChange: (mode: TransportMode) => void
}

export function Header({ locationStatus, mode, onModeChange }: HeaderProps) {
  return (
    <header>
      <h1>📍 TLV Bot</h1>
      <p className="location-status">{locationStatus}</p>
      <div className="mode-toggle" role="group" aria-label="Transport mode">
        <button
          type="button"
          className={mode === 'walking' ? 'active' : ''}
          onClick={() => onModeChange('walking')}
        >
          🚶 Walk
        </button>
        <button
          type="button"
          className={mode === 'driving' ? 'active' : ''}
          onClick={() => onModeChange('driving')}
        >
          🚗 Drive
        </button>
      </div>
    </header>
  )
}
