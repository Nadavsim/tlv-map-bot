import { ChevronDown, ChevronUp } from 'lucide-react'
import { useId, useState } from 'react'
import { getCategories } from '../api'
import { t } from '../i18n'
import type { Lang, SuggestOutcome } from '../types'

// Same limits the server enforces (it cleans and trims anyway).
const MAX_PLACE_CHARS = 300
const OTHER = 'other'

interface SuggestSpotProps {
  lang: Lang
  // Resolves to what happened, never throws (the caller maps errors).
  onSubmit: (place: string, category: string) => Promise<SuggestOutcome>
}

const OUTCOME_KEYS: Record<Exclude<SuggestOutcome, 'added'>, string> = {
  exists: 'suggestExists',
  daily_limit: 'suggestDailyLimit',
  pending_limit: 'suggestPendingLimit',
  too_fast: 'suggestTooFast',
  only_google_links: 'suggestOnlyGoogle',
  failed: 'suggestFailed',
}

// A signed-in visitor's private note to the curator: a place, and which
// category it belongs in. Collapsed until asked for, like the other drawer
// lists. Nothing here is shown to anyone else.
export function SuggestSpot({ lang, onSubmit }: SuggestSpotProps) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [categories, setCategories] = useState<string[] | null>(null)
  const [place, setPlace] = useState('')
  const [category, setCategory] = useState('')
  const [state, setState] = useState<'idle' | 'sending'>('idle')
  const [message, setMessage] = useState<{ key: string; ok: boolean } | null>(null)

  async function toggle() {
    const next = !open
    setOpen(next)
    setMessage(null)
    // The list is the map's own categories, fetched the first time it's needed.
    if (next && categories === null) {
      try {
        setCategories((await getCategories()).categories)
      } catch {
        setCategories([])
      }
    }
  }

  const canSend = state === 'idle' && place.trim() !== '' && category !== ''

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!canSend) return
    setState('sending')
    setMessage(null)
    const outcome = await onSubmit(place.trim(), category)
    setState('idle')
    if (outcome === 'added') {
      setMessage({ key: 'suggestThanks', ok: true })
      setPlace('')
      setCategory('')
    } else {
      setMessage({ key: OUTCOME_KEYS[outcome], ok: outcome === 'exists' })
      if (outcome === 'exists') {
        setPlace('')
        setCategory('')
      }
    }
  }

  return (
    <div className="saved-addresses suggest-spot">
      <button
        type="button"
        className="saved-addresses-toggle"
        aria-expanded={open}
        aria-controls={`${id}-form`}
        onClick={toggle}
      >
        <span>{t(lang, 'suggestHeading')}</span>
        {open ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
      </button>
      {open && (
        <form className="suggest-form" id={`${id}-form`} onSubmit={submit}>
          <label className="suggest-field" htmlFor={`${id}-place`}>
            <span>{t(lang, 'suggestPlaceLabel')}</span>
            <input
              id={`${id}-place`}
              type="text"
              value={place}
              maxLength={MAX_PLACE_CHARS}
              placeholder={t(lang, 'suggestPlacePlaceholder')}
              onChange={(e) => setPlace(e.target.value)}
              autoComplete="off"
              required
            />
          </label>
          <label className="suggest-field" htmlFor={`${id}-category`}>
            <span>{t(lang, 'suggestCategoryLabel')}</span>
            <select
              id={`${id}-category`}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              required
            >
              <option value="" disabled>
                {t(lang, 'suggestCategoryPlaceholder')}
              </option>
              {(categories ?? []).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
              <option value={OTHER}>{t(lang, 'suggestCategoryOther')}</option>
            </select>
          </label>
          <p className="saved-addresses-note">{t(lang, 'suggestPrivacy')}</p>
          <button type="submit" className="suggest-send" disabled={!canSend}>
            {state === 'sending' ? t(lang, 'suggestSending') : t(lang, 'suggestSend')}
          </button>
          {message && (
            <p className={`suggest-message${message.ok ? '' : ' is-error'}`} role="status">
              {t(lang, message.key as Parameters<typeof t>[1])}
            </p>
          )}
        </form>
      )}
    </div>
  )
}
