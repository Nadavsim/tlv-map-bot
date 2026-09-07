import { useEffect, useState } from 'react'
import { ApiError, getCategories, postChat, postMorePlaces } from './api'
import { type ChatEntry, makeEntryId } from './chatTypes'
import { ChatInput } from './components/ChatInput'
import { ChatLog } from './components/ChatLog'
import { Header } from './components/Header'
import { t } from './i18n'
import { loadLang, loadTheme, saveLang, saveTheme } from './preferences'
import type { Coordinates, Lang, Theme, TransportMode } from './types'
import { PAGE_SIZE } from './types'
import './styles/theme.css'
import './styles/App.css'

// Typing either word switches straight to the help flow, regardless of the
// current UI language - a user shouldn't need to guess which language the
// bot expects this one command in.
const HELP_COMMANDS = ['help', 'עזרה']

export default function App() {
  const [lang, setLang] = useState<Lang>(() => loadLang())
  const [theme, setTheme] = useState<Theme>(() => loadTheme())
  const [entries, setEntries] = useState<ChatEntry[]>(() => [
    { id: makeEntryId(), kind: 'bot-text', text: t(loadLang(), 'greeting') },
  ])
  const [locationStatus, setLocationStatus] = useState(() => t(loadLang(), 'locationRequesting'))
  const [userLocation, setUserLocation] = useState<Coordinates | null>(null)
  const [showLocationForm, setShowLocationForm] = useState(false)
  const [isRequestingLocation, setIsRequestingLocation] = useState(false)
  const [mode, setMode] = useState<TransportMode>('walking')
  const [isWaitingForReply, setIsWaitingForReply] = useState(false)
  const [loadingMoreId, setLoadingMoreId] = useState<string | null>(null)

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'he' ? 'rtl' : 'ltr'
    saveLang(lang)
  }, [lang])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    saveTheme(theme)
  }, [theme])

  function offerManualLocation(statusText: string) {
    setLocationStatus(statusText)
    setShowLocationForm(true)
    setEntries((prev) => [
      ...prev,
      { id: makeEntryId(), kind: 'bot-text', text: t(lang, 'locationFallbackMessage') },
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
      if (!isRetry) offerManualLocation(t(lang, 'locationUnsupported'))
      return
    }

    setIsRequestingLocation(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude })
        setLocationStatus(t(lang, 'locationSet'))
        setShowLocationForm(false)
        setIsRequestingLocation(false)
      },
      () => {
        setIsRequestingLocation(false)
        if (isRetry) {
          setLocationStatus(t(lang, 'locationRetryFailed'))
        } else {
          offerManualLocation(t(lang, 'locationDenied'))
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
    setLocationStatus(t(lang, 'locationSet'))
    setShowLocationForm(false)
  }

  function handleLocationError(message: string) {
    setEntries((prev) => [...prev, { id: makeEntryId(), kind: 'bot-text', text: message }])
  }

  async function showHelp(userMessageText: string | null) {
    if (userMessageText !== null) {
      setEntries((prev) => [...prev, { id: makeEntryId(), kind: 'user-text', text: userMessageText }])
    }

    let categoriesLine: string | null = null
    try {
      const { categories } = await getCategories()
      if (categories.length) categoriesLine = `${t(lang, 'helpCategoriesPrefix')} ${categories.join(', ')}.`
    } catch {
      // Fine to skip the live category list if this fails - the rest of the help text still stands.
    }

    // Several short bubbles read better than one big block of text.
    const helpBubbles = [
      `${t(lang, 'helpIntro')}\n\n${t(lang, 'helpCraving')}`,
      `${t(lang, 'helpSurprise')}\n\n${t(lang, 'helpResults')}`,
      `${t(lang, 'helpMode')}\n\n${t(lang, 'helpLocation')}`,
      t(lang, 'helpAgain'),
    ]
    if (categoriesLine) helpBubbles.push(categoriesLine)

    setEntries((prev) => [
      ...prev,
      ...helpBubbles.map((text): ChatEntry => ({ id: makeEntryId(), kind: 'bot-text', text })),
    ])
  }

  // The most recent places result in the conversation, if any - lets a
  // follow-up like "something else" continue that search (same category,
  // next page) without the user having to restate it. Deliberately just
  // derived from in-memory entries (not persisted) - a page reload starts
  // a fresh conversation, which is exactly the "short-lived" scope this
  // was meant to have.
  function getPreviousContext(): { category: string | null; offset: number } | null {
    for (let i = entries.length - 1; i >= 0; i--) {
      const entry = entries[i]
      if (entry.kind === 'places') return { category: entry.category, offset: entry.offset }
    }
    return null
  }

  async function handleSend(message: string) {
    if (!userLocation) return

    // Answered locally - free, instant, no LLM call needed for a fixed command.
    if (HELP_COMMANDS.includes(message.trim().toLowerCase())) {
      await showHelp(message)
      return
    }

    setEntries((prev) => [...prev, { id: makeEntryId(), kind: 'user-text', text: message }])
    setIsWaitingForReply(true)

    try {
      const previous = getPreviousContext()
      const data = await postChat({
        message,
        lat: userLocation.lat,
        lon: userLocation.lon,
        mode,
        lang,
        previous_category: previous?.category ?? null,
        previous_offset: previous?.offset ?? 0,
        has_previous_context: previous !== null,
      })
      setEntries((prev) => {
        const next: ChatEntry[] = [...prev, { id: makeEntryId(), kind: 'bot-text', text: data.reply }]
        if (data.places.length) {
          next.push({
            id: makeEntryId(),
            kind: 'places',
            places: data.places,
            category: data.category,
            offset: data.offset,
            hasMore: data.places.length >= PAGE_SIZE,
          })
        }
        return next
      })
    } catch (err) {
      const text =
        err instanceof ApiError && err.status === 429 ? t(lang, 'chatRateLimited') : t(lang, 'chatNetworkError')
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
        lang={lang}
        onLangChange={setLang}
        theme={theme}
        onThemeChange={setTheme}
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
        lang={lang}
      />
      <ChatInput disabled={chatDisabled} onSend={handleSend} lang={lang} />
    </div>
  )
}
