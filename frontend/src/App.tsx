import { useEffect, useState } from 'react'
import { postChat } from './api'
import { type ChatEntry, makeEntryId } from './chatTypes'
import { ChatInput } from './components/ChatInput'
import { ChatLog } from './components/ChatLog'
import { Header } from './components/Header'
import type { Coordinates, TransportMode } from './types'
import './styles/theme.css'
import './styles/App.css'

export default function App() {
  const [entries, setEntries] = useState<ChatEntry[]>([
    {
      id: makeEntryId(),
      kind: 'bot-text',
      text: "Hi! I'll find the closest spot from your Tel Aviv food map once I know where you are.",
    },
  ])
  const [locationStatus, setLocationStatus] = useState('Requesting your location...')
  const [userLocation, setUserLocation] = useState<Coordinates | null>(null)
  const [showLocationForm, setShowLocationForm] = useState(false)
  const [mode, setMode] = useState<TransportMode>('walking')
  const [isWaitingForReply, setIsWaitingForReply] = useState(false)

  useEffect(() => {
    if (!navigator.geolocation) {
      setLocationStatus("Geolocation isn't supported in this browser - enter a manual location below.")
      setShowLocationForm(true)
      return
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude })
        setLocationStatus('Location set. Ask away!')
      },
      () => {
        setLocationStatus('Location permission denied - enter your coordinates manually.')
        setShowLocationForm(true)
      },
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }, [])

  function handleLocationSet(coords: Coordinates) {
    setUserLocation(coords)
    setLocationStatus('Location set. Ask away!')
    setShowLocationForm(false)
  }

  function handleLocationError(message: string) {
    setEntries((prev) => [...prev, { id: makeEntryId(), kind: 'bot-text', text: message }])
  }

  async function handleSend(message: string) {
    if (!userLocation) return

    setEntries((prev) => [...prev, { id: makeEntryId(), kind: 'user-text', text: message }])
    setIsWaitingForReply(true)

    try {
      const data = await postChat({ message, lat: userLocation.lat, lon: userLocation.lon, mode })
      setEntries((prev) => {
        const next: ChatEntry[] = [...prev, { id: makeEntryId(), kind: 'bot-text', text: data.reply }]
        if (data.places.length) {
          next.push({ id: makeEntryId(), kind: 'places', places: data.places })
        }
        return next
      })
    } catch {
      setEntries((prev) => [
        ...prev,
        { id: makeEntryId(), kind: 'bot-text', text: "Couldn't reach the server - check your connection." },
      ])
    } finally {
      setIsWaitingForReply(false)
    }
  }

  const chatDisabled = !userLocation || isWaitingForReply

  return (
    <div className="app">
      <Header locationStatus={locationStatus} mode={mode} onModeChange={setMode} />
      <ChatLog
        entries={entries}
        isWaitingForReply={isWaitingForReply}
        showLocationForm={showLocationForm}
        onLocationSet={handleLocationSet}
        onLocationError={handleLocationError}
      />
      <ChatInput disabled={chatDisabled} onSend={handleSend} />
    </div>
  )
}
