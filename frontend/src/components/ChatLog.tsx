import { useEffect, useRef } from 'react'
import { t } from '../i18n'
import type { ChatEntry } from '../chatTypes'
import { ChatBubble } from './ChatBubble'
import { PlaceCards } from './PlaceCards'
import { TypingIndicator } from './TypingIndicator'
import { LocationForm } from './LocationForm'
import type { Coordinates, Lang, Place, SavedAddress } from '../types'

interface ChatLogProps {
  entries: ChatEntry[]
  isWaitingForReply: boolean
  showLocationForm: boolean
  onLocationSet: (coords: Coordinates, label: string) => void
  onLocationError: (message: string) => void
  onRetryLocation: () => void
  isRequestingLocation: boolean
  showLiveRetry: boolean
  onShowMore: (entryId: string) => void
  loadingMoreId: string | null
  onPickCraving: (prompt: string) => void
  queuedCraving: string | null
  onClearQueuedCraving: () => void
  savedAddresses: SavedAddress[]
  favoriteIds: ReadonlySet<string>
  onToggleFavorite: (place: Place) => void
  lang: Lang
}

export function ChatLog({
  entries,
  isWaitingForReply,
  showLocationForm,
  onLocationSet,
  onLocationError,
  onRetryLocation,
  isRequestingLocation,
  showLiveRetry,
  onShowMore,
  loadingMoreId,
  onPickCraving,
  queuedCraving,
  onClearQueuedCraving,
  savedAddresses,
  favoriteIds,
  onToggleFavorite,
  lang,
}: ChatLogProps) {
  const logRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const el = logRef.current
    // The start screen reads from its top; a conversation follows its end.
    if (el) el.scrollTop = entries.length === 0 ? 0 : el.scrollHeight
  }, [entries, isWaitingForReply, showLocationForm])

  return (
    <main className="chat-log" aria-live="polite" ref={logRef}>
      {entries.length === 0 && (
        // The start screen: replaces the old pinned greeting bubble. The
        // chips work before a location exists (a tap queues the craving).
        <section className="hero" aria-label="TLV Bot">
          <h2 className="hero-title">{t(lang, 'heroTitle')}</h2>
          <p className="hero-lede">{t(lang, 'heroLede')}</p>
          <div className="hero-chips">
            {[t(lang, 'introPrompt1'), t(lang, 'introPrompt2'), t(lang, 'introPrompt3')].map((prompt) => (
              <button
                key={prompt}
                type="button"
                className={`starter-chip${queuedCraving === prompt ? ' is-queued' : ''}`}
                aria-pressed={queuedCraving === prompt}
                disabled={isWaitingForReply}
                onClick={() => onPickCraving(prompt)}
              >
                {prompt}
              </button>
            ))}
          </div>
          {queuedCraving ? (
            <p className="hero-hint hero-queued" role="status">
              {t(lang, 'craving_queued').replace('{craving}', queuedCraving)}{' '}
              <button type="button" className="hero-clear" onClick={onClearQueuedCraving}>
                {t(lang, 'cancel')}
              </button>
            </p>
          ) : (
            <p className="hero-hint">{t(lang, 'heroHint')}</p>
          )}
          <nav className="hero-links" aria-label="About and privacy">
            <a href="/about" target="_blank" rel="noopener noreferrer">
              {t(lang, 'aboutLink')}
            </a>
            <a href="/privacy" target="_blank" rel="noopener noreferrer">
              {t(lang, 'privacyLink')}
            </a>
          </nav>
        </section>
      )}
      {entries.map((entry) => {
        switch (entry.kind) {
          case 'bot-text':
            return <ChatBubble key={entry.id} role="bot" text={entry.text} />
          case 'user-text':
            return <ChatBubble key={entry.id} role="user" text={entry.text} />
          case 'places':
            return (
              <PlaceCards
                key={entry.id}
                places={entry.places}
                origin={entry.origin}
                hasMore={entry.hasMore}
                isLoadingMore={loadingMoreId === entry.id}
                onShowMore={() => onShowMore(entry.id)}
                favoriteIds={favoriteIds}
                onToggleFavorite={onToggleFavorite}
                lang={lang}
              />
            )
        }
      })}
      {showLocationForm && (
        <LocationForm
          onLocationSet={onLocationSet}
          onError={onLocationError}
          onRetryLocation={onRetryLocation}
          isRequestingLocation={isRequestingLocation}
          showLiveRetry={showLiveRetry}
          savedAddresses={savedAddresses}
          lang={lang}
        />
      )}
      {isWaitingForReply && <TypingIndicator lang={lang} />}
    </main>
  )
}
