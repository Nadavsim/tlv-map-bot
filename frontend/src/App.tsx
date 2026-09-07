import { useEffect, useState } from 'react'
import { ApiError, getCategories, postChat, postMorePlaces } from './api'
import { type ChatEntry, makeEntryId } from './chatTypes'
import { ChatInput } from './components/ChatInput'
import { ChatLog } from './components/ChatLog'
import { Header } from './components/Header'
import type { Coordinates, TransportMode } from './types'
import { PAGE_SIZE } from './types'

const HELP_TEXT = `Here's how I work:

- Tell me what you're craving - e.g. "ramen" or "coffee" - and I'll find the closest match from my curated Tel Aviv map.
- Say "surprise me" or "anything" for the closest spot no matter the category.
- Each answer shows distance, ETA, a one-tap navigation link, and Instagram when I have it. Tap "Show more" for further matches, or "Share" to send them to WhatsApp.
- Use the Walk / Drive toggle up top to switch how ETAs are calculated.
- No location? Use "Try enabling location again", or type an address, a Google Maps link, or coordinates instead.
- Type "help" any time to see this again.`
import './styles/theme.css'
import './styles/App.css'

export default function App() {
  const [entries, setEntries] = useState<ChatEntry[]>([
    {
      id: makeEntryId(),
      kind: 'bot-text',
      text: "Hi! I'll find the closest spot from your Tel Aviv food map. Please allow location access when your browser asks, so I know where you are! 📍",
    },
  ])
  const [locationStatus, setLocationStatus] = useState('Requesting your location...')
  const [userLocation, setUserLocation] = useState<Coordinates | null>(null)
  const [showLocationForm, setShowLocationForm] = useState(false)
  const [isRequestingLocation, setIsRequestingLocation] = useState(false)
  const [mode, setMode] = useState<TransportMode>('walking')
  const [isWaitingForReply, setIsWaitingForReply] = useState(false)
  const [loadingMoreId, setLoadingMoreId] = useState<string | null>(null)

  function offerManualLocation(statusText: string) {
    setLocationStatus(statusText)
    setShowLocationForm(true)
    setEntries((prev) => [
      ...prev,
      {
        id: makeEntryId(),
        kind: 'bot-text',
        text: "No worries - please enable location access, or enter an address, a Google Maps link, or your coordinates below and I'll use that instead.",
      },
    ])
  }

  // isRetry=false (initial mount attempt): a failure pushes the full
  // explanatory chat message + shows the manual-entry form. isRetry=true
  // (the "try again" button, after the form is already showing - e.g. the
  // user enabled location in settings after initially denying it, which
  // otherwise required a page reload to take effect): a failure just
  // updates the status line instead of spamming another chat bubble.
  function requestLocation(isRetry: boolean) {
    if (!navigator.geolocation) {
      if (!isRetry) offerManualLocation("Geolocation isn't supported in this browser.")
      return
    }

    setIsRequestingLocation(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude })
        setLocationStatus('Location set. Ask away!')
        setShowLocationForm(false)
        setIsRequestingLocation(false)
      },
      () => {
        setIsRequestingLocation(false)
        if (isRetry) {
          setLocationStatus('Still no access - try again, or use the box below.')
        } else {
          offerManualLocation('Location permission denied.')
        }
      },
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  useEffect(() => {
    requestLocation(false)
  }, [])

  function handleLocationSet(coords: Coordinates) {
    setUserLocation(coords)
    setLocationStatus('Location set. Ask away!')
    setShowLocationForm(false)
  }

  function handleLocationError(message: string) {
    setEntries((prev) => [...prev, { id: makeEntryId(), kind: 'bot-text', text: message }])
  }

  async function showHelp(userMessageText: string | null) {
    if (userMessageText !== null) {
      setEntries((prev) => [...prev, { id: makeEntryId(), kind: 'user-text', text: userMessageText }])
    }

    let categoriesLine = ''
    try {
      const { categories } = await getCategories()
      if (categories.length) categoriesLine = `\n\nCategories I currently know about: ${categories.join(', ')}.`
    } catch {
      // Fine to skip the live category list if this fails - the rest of the help text still stands.
    }

    setEntries((prev) => [...prev, { id: makeEntryId(), kind: 'bot-text', text: HELP_TEXT + categoriesLine }])
  }

  async function handleSend(message: string) {
    if (!userLocation) return

    // Answered locally - free, instant, no LLM call needed for a fixed command.
    if (message.trim().toLowerCase() === 'help') {
      await showHelp(message)
      return
    }

    setEntries((prev) => [...prev, { id: makeEntryId(), kind: 'user-text', text: message }])
    setIsWaitingForReply(true)

    try {
      const data = await postChat({ message, lat: userLocation.lat, lon: userLocation.lon, mode })
      setEntries((prev) => {
        const next: ChatEntry[] = [...prev, { id: makeEntryId(), kind: 'bot-text', text: data.reply }]
        if (data.places.length) {
          next.push({
            id: makeEntryId(),
            kind: 'places',
            places: data.places,
            category: data.category,
            offset: data.places.length,
            hasMore: data.places.length >= PAGE_SIZE,
          })
        }
        return next
      })
    } catch (err) {
      const text =
        err instanceof ApiError && err.status === 429
          ? "You're sending messages a bit fast - give it a moment and try again."
          : "Couldn't reach the server - check your connection."
      setEntries((prev) => [...prev, { id: makeEntryId(), kind: 'bot-text', text }])
    } finally {
      setIsWaitingForReply(false)
    }
  }

  async function handleShowMore(entryId: string) {
    const entry = entries.find((e) => e.id === entryId)
    if (!entry || entry.kind !== 'places' || !userLocation) return

    setLoadingMoreId(entryId)
    try {
      const data = await postMorePlaces({
        category: entry.category,
        lat: userLocation.lat,
        lon: userLocation.lon,
        mode,
        offset: entry.offset,
      })
      setEntries((prev) =>
        prev.map((e) =>
          e.id === entryId && e.kind === 'places'
            ? {
                ...e,
                places: [...e.places, ...data.places],
                offset: e.offset + data.places.length,
                hasMore: data.places.length >= PAGE_SIZE,
              }
            : e,
        ),
      )
    } catch {
      // Leave hasMore as-is so the button stays put and the user can retry.
    } finally {
      setLoadingMoreId(null)
    }
  }

  const chatDisabled = !userLocation || isWaitingForReply

  return (
    <div className="app">
      <Header
        locationStatus={locationStatus}
        mode={mode}
        onModeChange={setMode}
        onHelp={() => showHelp(null)}
      />
      <ChatLog
        entries={entries}
        isWaitingForReply={isWaitingForReply}
        showLocationForm={showLocationForm}
        onLocationSet={handleLocationSet}
        onLocationError={handleLocationError}
        onRetryLocation={() => requestLocation(true)}
        isRequestingLocation={isRequestingLocation}
        onShowMore={handleShowMore}
        loadingMoreId={loadingMoreId}
      />
      <ChatInput disabled={chatDisabled} onSend={handleSend} />
    </div>
  )
}
