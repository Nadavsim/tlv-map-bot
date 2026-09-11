import { LocateFixed } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { resolveLocation } from '../api'
import { t } from '../i18n'
import type { Coordinates, Lang } from '../types'

interface LocationFormProps {
  onLocationSet: (coords: Coordinates, label: string) => void
  onError: (message: string) => void
  onRetryLocation: () => void
  isRequestingLocation: boolean
  lang: Lang
}

export function LocationForm({
  onLocationSet,
  onError,
  onRetryLocation,
  isRequestingLocation,
  lang,
}: LocationFormProps) {
  const [value, setValue] = useState('')
  const [isResolving, setIsResolving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const text = value.trim()
    if (!text) return

    const parts = text.split(',').map((s) => parseFloat(s.trim()))
    if (parts.length === 2 && !parts.some(Number.isNaN)) {
      onLocationSet({ lat: parts[0], lon: parts[1] }, text)
      return
    }

    // Anything else - a Maps link or a free-text address/landmark - goes
    // through the same backend endpoint, which tries link extraction first
    // and falls back to geocoding it as an address.
    setIsResolving(true)
    try {
      const data = await resolveLocation(text)
      if (data.lat == null || data.lon == null) {
        onError(t(lang, 'locationResolveError'))
        return
      }
      onLocationSet({ lat: data.lat, lon: data.lon }, text)
    } catch {
      onError(t(lang, 'locationResolveNetworkError'))
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
        {isRequestingLocation ? t(lang, 'locationUseLiveButtonChecking') : t(lang, 'locationUseLiveButton')}
      </button>
      <form className="location-form-row" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder={t(lang, 'locationInputPlaceholder')}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <button type="submit" disabled={isResolving}>
          {isResolving ? '...' : t(lang, 'locationSetButton')}
        </button>
      </form>
    </div>
  )
}
