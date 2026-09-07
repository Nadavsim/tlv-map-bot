import { LocateFixed } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { resolveLocation } from '../api'
import type { Coordinates } from '../types'

interface LocationFormProps {
  onLocationSet: (coords: Coordinates) => void
  onError: (message: string) => void
  onRetryLocation: () => void
  isRequestingLocation: boolean
}

export function LocationForm({
  onLocationSet,
  onError,
  onRetryLocation,
  isRequestingLocation,
}: LocationFormProps) {
  const [value, setValue] = useState('')
  const [isResolving, setIsResolving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const text = value.trim()
    if (!text) return

    const parts = text.split(',').map((s) => parseFloat(s.trim()))
    if (parts.length === 2 && !parts.some(Number.isNaN)) {
      onLocationSet({ lat: parts[0], lon: parts[1] })
      return
    }

    // Anything else - a Maps link or a free-text address/landmark - goes
    // through the same backend endpoint, which tries link extraction first
    // and falls back to geocoding it as an address.
    setIsResolving(true)
    try {
      const data = await resolveLocation(text)
      if (data.lat == null || data.lon == null) {
        onError("Couldn't find that location - try a Maps link, coordinates, or a more specific address.")
        return
      }
      onLocationSet({ lat: data.lat, lon: data.lon })
    } catch {
      onError("Couldn't reach the server to resolve that - try again.")
    } finally {
      setIsResolving(false)
    }
  }

  return (
    <div className="location-fallback">
      <button
        type="button"
        className="retry-location-button"
        onClick={onRetryLocation}
        disabled={isRequestingLocation}
      >
        <LocateFixed size={15} aria-hidden="true" />
        {isRequestingLocation ? 'Checking...' : 'Try enabling location again'}
      </button>
      <form className="location-form-row" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Coordinates, a Maps link, or an address"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <button type="submit" disabled={isResolving}>
          {isResolving ? '...' : 'Set'}
        </button>
      </form>
    </div>
  )
}
