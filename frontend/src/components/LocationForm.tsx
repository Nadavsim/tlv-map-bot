import { LocateFixed, MapPin } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { resolveLocation } from '../api'
import { t } from '../i18n'
import type { Coordinates, Lang, SavedAddress } from '../types'

interface LocationFormProps {
  onLocationSet: (coords: Coordinates, label: string) => void
  onError: (message: string) => void
  onRetryLocation: () => void
  isRequestingLocation: boolean
  // Live mode has nothing to type - it only ever needs a way to ask the
  // browser again. Custom mode has nothing to retry - it only ever needs
  // the address input. Showing both together is what let a click on "Use
  // my current location" silently hijack an in-progress Custom session
  // back to Live.
  showLiveRetry: boolean
  // The signed-in person's saved addresses - a tap sets the location straight
  // from the stored coordinates, with no address lookup at all.
  savedAddresses: SavedAddress[]
  lang: Lang
}

export function LocationForm({
  onLocationSet,
  onError,
  onRetryLocation,
  isRequestingLocation,
  showLiveRetry,
  savedAddresses,
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
        // A link that gave nothing needs different advice from a typed
        // address that gave nothing - "check the spelling" is no use for it.
        onError(t(lang, /^https?:\/\//i.test(text) ? 'locationLinkError' : 'locationResolveError'))
        return
      }
      onLocationSet({ lat: data.lat, lon: data.lon }, data.label || text)
    } catch {
      onError(t(lang, 'locationResolveNetworkError'))
    } finally {
      setIsResolving(false)
    }
  }

  if (showLiveRetry) {
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
      </div>
    )
  }

  return (
    <div className="location-fallback">
      {savedAddresses.length > 0 && (
        <div className="saved-address-chips" role="group" aria-label={t(lang, 'savedAddressesHeading')}>
          {savedAddresses.map((address) => (
            <button
              key={address.id}
              type="button"
              className="saved-address-chip"
              onClick={() => onLocationSet({ lat: address.lat, lon: address.lon }, address.label)}
            >
              <MapPin size={14} aria-hidden="true" />
              {address.label}
            </button>
          ))}
        </div>
      )}
      <form className="location-form-row" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder={t(lang, 'locationInputPlaceholder')}
          value={value}
          maxLength={500}
          onChange={(e) => setValue(e.target.value)}
        />
        <button type="submit" disabled={isResolving}>
          {isResolving ? '...' : t(lang, 'locationSetButton')}
        </button>
      </form>
    </div>
  )
}
