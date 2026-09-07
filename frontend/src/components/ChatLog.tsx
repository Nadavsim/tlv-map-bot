import { useEffect, useRef } from 'react'
import type { ChatEntry } from '../chatTypes'
import { ChatBubble } from './ChatBubble'
import { PlaceCards } from './PlaceCards'
import { TypingIndicator } from './TypingIndicator'
import { LocationForm } from './LocationForm'
import type { Coordinates } from '../types'

interface ChatLogProps {
  entries: ChatEntry[]
  isWaitingForReply: boolean
  showLocationForm: boolean
  onLocationSet: (coords: Coordinates) => void
  onLocationError: (message: string) => void
}

export function ChatLog({
  entries,
  isWaitingForReply,
  showLocationForm,
  onLocationSet,
  onLocationError,
}: ChatLogProps) {
  const logRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [entries, isWaitingForReply, showLocationForm])

  return (
    <main className="chat-log" aria-live="polite" ref={logRef}>
      {entries.map((entry) => {
        switch (entry.kind) {
          case 'bot-text':
            return <ChatBubble key={entry.id} role="bot" text={entry.text} />
          case 'user-text':
            return <ChatBubble key={entry.id} role="user" text={entry.text} />
          case 'places':
            return <PlaceCards key={entry.id} places={entry.places} />
        }
      })}
      {showLocationForm && (
        <LocationForm onLocationSet={onLocationSet} onError={onLocationError} />
      )}
      {isWaitingForReply && <TypingIndicator />}
    </main>
  )
}
