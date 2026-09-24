import { useEffect, useRef, useState } from 'react'
import { ApiError, getAuthConfig, getCategories, postChat, postGoogleAuth, postLogout, postMorePlaces, postRefresh } from './api'
import { type ChatEntry, makeEntryId } from './chatTypes'
import { ChatInput } from './components/ChatInput'
import { ChatLog } from './components/ChatLog'
import { Header } from './components/Header'
import { t, type StringKey } from './i18n'
import { loadLang, loadTheme, saveLang, saveTheme } from './preferences'
import type { AuthUser, Coordinates, Lang, LocationMode, Theme, TransportMode } from './types'
import { PAGE_SIZE } from './types'
import './styles/theme.css'
import './styles/App.css'

// Typing either word switches straight to the help flow, regardless of the
// current UI language - a user shouldn't need to guess which language the
// bot expects this one command in.
const HELP_COMMANDS = ['help', 'עזרה']

// Not in the DOM lib's standard event types (it's a Chromium-only, still
// non-standard event) - just enough of the shape this app actually uses.
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
}

// How long an accidental "New Conversation" tap stays undoable.
const UNDO_WINDOW_MS = 5000

// Refresh a bit before the access token's real 15-minute expiry (backend's
// ACCESS_TOKEN_TTL_SECONDS) - a safety margin, not an exact mirror of it, so
// a slow request right at the boundary doesn't get a token that expires
// mid-flight.
const ACCESS_TOKEN_REFRESH_MS = 14 * 60 * 1000

// The location status line is live UI chrome (like the Walk/Drive labels),
// not a chat message - it should always reflect the *current* language, not
// whatever language was active the moment it was last set. Storing the i18n
// key (not the already-translated text) and translating it at render time
// is what makes that happen automatically on a language switch.
type LocationStatusKey = Extract<
  StringKey,
  | 'locationNotSet'
  | 'locationRequesting'
  | 'locationSet'
  | 'locationDenied'
  | 'locationUnavailable'
  | 'locationTimeout'
  | 'locationUnsupported'
>

export default function App() {
  const [lang, setLang] = useState<Lang>(() => loadLang())
  const [theme, setTheme] = useState<Theme>(() => loadTheme())
  const [entries, setEntries] = useState<ChatEntry[]>([])
  const [locationStatusKey, setLocationStatusKey] = useState<LocationStatusKey>('locationNotSet')
  const [liveLocation, setLiveLocation] = useState<Coordinates | null>(null)
  const [manualLocation, setManualLocation] = useState<Coordinates | null>(null)
  const [manualLocationLabel, setManualLocationLabel] = useState<string | null>(null)
  // Custom is the default - no browser permission prompt until the user
  // deliberately asks for Live, rather than firing one automatically on
  // load. The address form starts open to match: there's nothing to enter
  // yet either way.
  const [locationMode, setLocationMode] = useState<LocationMode>('manual')
  const [showLocationForm, setShowLocationForm] = useState(true)
  const [isRequestingLocation, setIsRequestingLocation] = useState(false)
  const [mode, setMode] = useState<TransportMode>('walking')
  const [isWaitingForReply, setIsWaitingForReply] = useState(false)
  const [loadingMoreId, setLoadingMoreId] = useState<string | null>(null)
  const [clearedEntries, setClearedEntries] = useState<ChatEntry[] | null>(null)
  const undoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [googleClientId, setGoogleClientId] = useState<string | null>(null)
  // Never triggers a re-render on its own (only authUser does) - this is
  // exactly why it's a ref and not state: nothing in the UI reads the raw
  // token value itself, only whether someone is signed in.
  const accessTokenRef = useRef<string | null>(null)
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // The browser's own automatic install banner is suppressed (preventDefault
  // below) in favor of firing it ourselves at a more deliberate moment - the
  // warmest one available: right after a visitor who arrived via a shared
  // link gets their first real result, not on generic first load.
  const deferredInstallPromptRef = useRef<BeforeInstallPromptEvent | null>(null)
  const cameFromShareRef = useRef(false)
  const hasPromptedInstallRef = useRef(false)

  useEffect(() => {
    return () => {
      if (undoTimerRef.current) clearTimeout(undoTimerRef.current)
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
    }
  }, [])

  useEffect(() => {
    cameFromShareRef.current = new URLSearchParams(window.location.search).get('src') === 'share'

    function handleBeforeInstallPrompt(e: Event) {
      e.preventDefault()
      deferredInstallPromptRef.current = e as BeforeInstallPromptEvent
    }
    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt)
    return () => window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt)
  }, [])

  // Fires once, the moment both conditions are actually true - the browser
  // may not have offered a deferred prompt yet when the first result lands
  // (or ever, if it's already installed/ineligible), so this re-checks on
  // every entries change rather than only right after sending a message.
  useEffect(() => {
    if (!cameFromShareRef.current || hasPromptedInstallRef.current) return
    const deferred = deferredInstallPromptRef.current
    if (!deferred) return
    const hasGoodResult = entries.some((entry) => entry.kind === 'places' && entry.places.length > 0)
    if (!hasGoodResult) return

    hasPromptedInstallRef.current = true
    deferredInstallPromptRef.current = null
    deferred.prompt()
  }, [entries])

  // The Client ID isn't secret, but it lives in the backend's env rather
  // than being duplicated into a frontend build-time config - one source of
  // truth, same reasoning as fetching /api/categories instead of hardcoding.
  useEffect(() => {
    getAuthConfig()
      .then(({ google_client_id }) => setGoogleClientId(google_client_id))
      .catch(() => {
        // No Sign-In button if this fails - the rest of the app (the actual
        // core feature) doesn't depend on it.
      })
  }, [])

  // Restores a session on load using the httpOnly refresh cookie, if one
  // exists - a fresh visitor with no cookie gets a clean 401 here, which
  // postRefresh() already turns into a plain `null`, not a thrown error.
  useEffect(() => {
    postRefresh()
      .then((result) => {
        if (result) applySession(result.access_token, result.user)
      })
      .catch(() => {
        // Silent - an anonymous visitor is the default, expected state.
      })
  }, [])

  function applySession(accessToken: string, user: AuthUser) {
    accessTokenRef.current = accessToken
    setAuthUser(user)
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
    refreshTimerRef.current = setTimeout(async () => {
      try {
        const result = await postRefresh()
        if (result) {
          applySession(result.access_token, result.user)
        } else {
          // The refresh cookie itself expired/was revoked - fall back to
          // signed-out rather than silently keeping a stale access token.
          accessTokenRef.current = null
          setAuthUser(null)
        }
      } catch {
        // A network hiccup shouldn't sign someone out - just try again on
        // the same schedule next time rather than tearing down the session.
      }
    }, ACCESS_TOKEN_REFRESH_MS)
  }

  async function handleGoogleCredential(credential: string) {
    try {
      const result = await postGoogleAuth(credential)
      applySession(result.access_token, result.user)
    } catch {
      // Sign-in failing shouldn't be a chat-log error bubble - it's not part
      // of that conversation. Silently staying signed out is the safe
      // fallback; nothing in the app currently depends on being signed in.
    }
  }

  async function handleSignOut() {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
    accessTokenRef.current = null
    setAuthUser(null)
    await postLogout().catch(() => {
      // Already signed out client-side regardless - a failed request here
      // just means the server-side session lingers until its own expiry.
    })
  }

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'he' ? 'rtl' : 'ltr'
    saveLang(lang)
  }, [lang])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    saveTheme(theme)
  }, [theme])

  // Only ever called in direct response to the user asking for Live (the
  // toggle, or the form's "Use my current location" button) - there's no
  // silent background attempt to distinguish from a retry anymore, since
  // Custom is the default and nothing requests geolocation on its own.
  function requestLocation() {
    if (!navigator.geolocation) {
      setLocationStatusKey('locationUnsupported')
      setShowLocationForm(true)
      return
    }

    setIsRequestingLocation(true)
    setLocationStatusKey('locationRequesting')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLiveLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude })
        setLocationStatusKey('locationSet')
        setLocationMode('live')
        setShowLocationForm(false)
        setIsRequestingLocation(false)
      },
      (error) => {
        setIsRequestingLocation(false)
        setShowLocationForm(true)
        // These three codes are genuinely different problems and were
        // previously collapsed into one "check your permissions" message -
        // which is actively misleading for the latter two, neither of
        // which has anything to do with permissions. TIMEOUT in particular
        // is the likely everyday case indoors with enableHighAccuracy
        // (GPS can easily take longer than 10-20s to get a fix, or never
        // get one at all inside a building), and no amount of permission
        // troubleshooting can fix that.
        if (error.code === error.POSITION_UNAVAILABLE) {
          setLocationStatusKey('locationUnavailable')
        } else if (error.code === error.TIMEOUT) {
          setLocationStatusKey('locationTimeout')
        } else {
          setLocationStatusKey('locationDenied')
        }
      },
      // enableHighAccuracy (GPS) was causing real-world timeouts that got
      // misreported as permission problems - this app only needs "which
      // nearby place is closest," not turn-by-turn precision, so the
      // faster, more reliable network/wifi-based fix (the default) is the
      // better trade-off. A generous 20s timeout as a safety net either way.
      { enableHighAccuracy: false, timeout: 20000 },
    )
  }

  // Fires whenever the address/Maps-link/coordinates form is submitted -
  // whether it's showing by default, because a Live attempt failed, or
  // because the user deliberately opened it via the Live/Custom toggle or
  // "Change" below. Either way, the result is the same: a manual location,
  // now active.
  function handleLocationSet(coords: Coordinates, label: string) {
    setManualLocation(coords)
    setManualLocationLabel(label)
    setLocationMode('manual')
    setShowLocationForm(false)
  }

  // The toggle always reflects the click immediately - `setLocationMode`
  // fires unconditionally before anything else, so it never waits on an
  // async result (a pending geolocation request) to look pressed.
  // Live: reuse the last known fix instantly if there is one, otherwise
  // request a fresh one - the browser's permission prompt only ever
  // appears here, never automatically. Custom: reactivate the last
  // manual location instantly if there is one, otherwise open the form -
  // `handleLocationSet` above is what stores a newly-submitted address.
  function handleLocationModeChange(newMode: LocationMode) {
    if (newMode === locationMode) return
    setLocationMode(newMode)
    if (newMode === 'live') {
      if (liveLocation) {
        setShowLocationForm(false)
      } else {
        requestLocation()
      }
    } else {
      setShowLocationForm(!manualLocation)
    }
  }

  function handleChangeManualLocation() {
    setShowLocationForm(true)
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
  function getPreviousContext(): { category: string | null; dietaryTag: string | null; offset: number } | null {
    for (let i = entries.length - 1; i >= 0; i--) {
      const entry = entries[i]
      if (entry.kind === 'places') {
        return { category: entry.category, dietaryTag: entry.dietaryTag, offset: entry.offset }
      }
    }
    return null
  }

  async function handleSend(message: string) {
    if (!activeLocation) return

    // Continuing the conversation forfeits any pending undo - restoring the
    // cleared history at this point would silently discard whatever the user
    // just sent instead.
    dismissUndo()

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
        lat: activeLocation.lat,
        lon: activeLocation.lon,
        mode,
        lang,
        previous_category: previous?.category ?? null,
        previous_dietary_tag: previous?.dietaryTag ?? null,
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
            dietaryTag: data.dietary_tag,
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
    if (!entry || entry.kind !== 'places' || !activeLocation) return

    setLoadingMoreId(entryId)
    try {
      const data = await postMorePlaces({
        category: entry.category,
        tag: entry.dietaryTag,
        lat: activeLocation.lat,
        lon: activeLocation.lon,
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

  function dismissUndo() {
    if (undoTimerRef.current) {
      clearTimeout(undoTimerRef.current)
      undoTimerRef.current = null
    }
    setClearedEntries(null)
  }

  // Clears the conversation only - location/theme/language are separate
  // state and deliberately untouched, so "starting over" doesn't also throw
  // away location permission or preferences. The cleared history is kept
  // around briefly so an accidental tap (the header icons sit close
  // together) can be undone instead of silently losing results.
  function handleNewConversation() {
    if (entries.length === 0) return
    setClearedEntries(entries)
    setEntries([])
    if (undoTimerRef.current) clearTimeout(undoTimerRef.current)
    undoTimerRef.current = setTimeout(() => setClearedEntries(null), UNDO_WINDOW_MS)
  }

  function handleUndoClear() {
    if (!clearedEntries) return
    setEntries(clearedEntries)
    dismissUndo()
  }

  // Manual mode echoes back exactly what the user typed (a location label,
  // not a place name) rather than a translated string - deliberately
  // unmediated, same reasoning as place names never being translated.
  const activeLocation = locationMode === 'manual' ? manualLocation : liveLocation
  const chatDisabled = !activeLocation || isWaitingForReply
  const canChangeManualLocation = locationMode === 'manual' && manualLocation !== null && !showLocationForm
  const locationStatusText =
    locationMode === 'manual' && manualLocationLabel
      ? `${t(lang, 'locationActiveManualPrefix')} ${manualLocationLabel}`
      : t(lang, locationStatusKey)

  return (
    <div className="app">
      <Header
        locationStatus={locationStatusText}
        locationMode={locationMode}
        onLocationModeChange={handleLocationModeChange}
        canChangeManualLocation={canChangeManualLocation}
        onChangeManualLocation={handleChangeManualLocation}
        mode={mode}
        onModeChange={setMode}
        onHelp={() => showHelp(null)}
        onNewConversation={handleNewConversation}
        lang={lang}
        onLangChange={setLang}
        theme={theme}
        onThemeChange={setTheme}
        authUser={authUser}
        googleClientId={googleClientId}
        onGoogleCredential={handleGoogleCredential}
        onSignOut={handleSignOut}
      />
      <ChatLog
        greeting={t(lang, 'greeting')}
        entries={entries}
        isWaitingForReply={isWaitingForReply}
        showLocationForm={showLocationForm}
        onLocationSet={handleLocationSet}
        onLocationError={handleLocationError}
        onRetryLocation={() => {
          setLocationMode('live')
          requestLocation()
        }}
        isRequestingLocation={isRequestingLocation}
        showLiveRetry={locationMode === 'live'}
        onShowMore={handleShowMore}
        loadingMoreId={loadingMoreId}
        lang={lang}
      />
      {clearedEntries && (
        <div className="undo-toast" role="status">
          <span>{t(lang, 'conversationCleared')}</span>
          <button type="button" onClick={handleUndoClear}>
            {t(lang, 'undo')}
          </button>
        </div>
      )}
      <ChatInput disabled={chatDisabled} onSend={handleSend} lang={lang} />
      <footer className="app-footer">
        {/* Opens in a new tab so navigating there doesn't lose the current,
            in-memory-only conversation (there's no persistence to return to). */}
        <a href="/privacy" target="_blank" rel="noopener noreferrer">
          {t(lang, 'privacyLink')}
        </a>
      </footer>
    </div>
  )
}
