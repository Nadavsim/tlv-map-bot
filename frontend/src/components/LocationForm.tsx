import { useState, type FormEvent } from 'react'
import { resolveLocation } from '../api'
import type { Coordinates } from '../types'

interface LocationFormProps {
  onLocationSet: (coords: Coordinates) => void
  onError: (message: string) => void
}

export function LocationForm({ onLocationSet, onError }: LocationFormProps) {
  const [value, setValue] = useState('')
  const [isResolving, setIsResolving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const text = value.trim()

    const parts = text.split(',').map((s) => parseFloat(s.trim()))
    if (parts.length === 2 && !parts.some(Number.isNaN)) {
      onLocationSet({ lat: parts[0], lon: parts[1] })
      return
    }

    if (!text.includes('http://') && !text.includes('https://')) {
      onError("That doesn't look like 'lat, lon' or a Maps link - try again.")
      return
    }

    setIsResolving(true)
    try {
      const data = await resolveLocation(text)
      if (data.lat == null || data.lon == null) {
        onError("Couldn't find coordinates in that link - try pasting the coordinates directly instead.")
        return
      }
      onLocationSet({ lat: data.lat, lon: data.lon })
    } catch {
      onError("Couldn't reach the server to resolve that link - try again.")
    } finally {
      setIsResolving(false)
    }
  }

  return (
    <form className="location-form-row" onSubmit={handleSubmit}>
      <input
        type="text"
        placeholder="Paste coordinates or a Google Maps link"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button type="submit" disabled={isResolving}>
        {isResolving ? '...' : 'Set'}
      </button>
    </form>
  )
}
