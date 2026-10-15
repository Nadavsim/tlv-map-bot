import { Banknote, Camera, Clock, Heart, MessageCircle, Navigation, Umbrella } from 'lucide-react'
import { useState } from 'react'
import { postPlaceReport } from '../api'
import { t } from '../i18n'
import type { Lang, Place, ReportKind } from '../types'

// "23" -> "23:00" - the raw hour this app stores/sends, formatted the one
// way a chip actually needs to show it.
function formatClosesAt(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`
}

interface PlaceCardProps {
  place: Place
  lang: Lang
  // Only set while the entry's map is open: the card then shows its pin's
  // number and can be selected to highlight that pin (and vice versa).
  mapNumber?: number
  isActive?: boolean
  onSelect?: () => void
  isFavorite?: boolean
  // Absent = no heart (never the case in the app; keeps the card reusable).
  onToggleFavorite?: () => void
}

export function PlaceCard({
  place,
  lang,
  mapNumber,
  isActive = false,
  onSelect,
  isFavorite = false,
  onToggleFavorite,
}: PlaceCardProps) {
  // "Report a problem" is a small inline two-option step inside the card, not
  // a dialog. 'sent' is final for this card for as long as it's on screen.
  const [reportStep, setReportStep] = useState<'idle' | 'choosing' | 'sending' | 'failed' | 'sent'>('idle')

  // What was sent, so the thank-you can match it ("I'd go back" is good news,
  // the other two aren't).
  const [sentKind, setSentKind] = useState<ReportKind | null>(null)

  async function sendReport(kind: ReportKind) {
    if (!place.id) return
    setReportStep('sending')
    try {
      await postPlaceReport(place.id, kind)
      setSentKind(kind)
      setReportStep('sent')
    } catch {
      setReportStep('failed')
    }
  }

  return (
    <div className={`place-card${isActive ? ' is-active' : ''}`} onClick={onSelect}>
      <div className="name">
        {mapNumber !== undefined && (
          // A real button (not just the card's click handler) so the link to
          // the pin is reachable by keyboard and screen readers too.
          <button
            type="button"
            className={`place-number${isActive ? ' is-active' : ''}`}
            aria-label={`${t(lang, 'showOnMapPin')} ${mapNumber}`}
            aria-pressed={isActive}
            onClick={onSelect}
          >
            {mapNumber}
          </button>
        )}
        {place.name}
      </div>
      <div className="meta">
        <span className="category-chip">{place.category}</span>
        {place.price_tier && (
          // A distinct icon (not shared with category/tag chips) so it
          // reads as a different kind of fact at a glance, not another tag.
          // aria-label (not just title, which never fires on touch) gives
          // screen readers a real accessible name instead of reading the
          // bare "$" characters as unexplained punctuation. dir="ltr"
          // mirrors .distance-eta just below - today's $/$$/$$$ glyphs are
          // palindromic so it's not visibly broken without this, but it's
          // the same class of RTL-in-a-bidi-document content that caused
          // this project's first-ever RTL bug.
          <span
            className="price-chip"
            title={t(lang, 'priceLabel')}
            aria-label={`${t(lang, 'priceLabel')}: ${place.price_tier}`}
            dir="ltr"
          >
            <Banknote size={12} aria-hidden="true" />
            {place.price_tier}
          </span>
        )}
        {place.dietary_tags.map((tag) => (
          <span className="tag-chip" key={tag}>
            {tag}
          </span>
        ))}
        {place.closes_at_hour !== null && (
          <span
            className="hours-chip"
            title={t(lang, 'closesAtLabel')}
            aria-label={`${t(lang, 'closesAtLabel')}: ${formatClosesAt(place.closes_at_hour)}`}
            dir="ltr"
          >
            <Clock size={12} aria-hidden="true" />
            {formatClosesAt(place.closes_at_hour)}
          </span>
        )}
        {place.outdoor_seating && (
          <span className="outdoor-chip" title={t(lang, 'outdoorSeatingLabel')}>
            <Umbrella size={12} aria-hidden="true" />
            {t(lang, 'outdoorSeatingLabel')}
          </span>
        )}
        <span className="distance-eta" dir="ltr">
          {place.etaPending ? (
            // Distance is already known; only the travel time is on its way.
            // A fixed-size placeholder (not "..." text) so the line doesn't
            // jump when the time arrives.
            <>
              {place.distance} <span aria-hidden="true">·</span>{' '}
              <span className="eta-placeholder" role="status" aria-label={t(lang, 'etaLoading')} />
            </>
          ) : place.eta ? (
            `${place.distance} · ${place.eta}`
          ) : (
            place.distance
          )}
        </span>
      </div>
      <div className="links">
        {place.id && onToggleFavorite && (
          // stopPropagation: the whole card is a click target for the map's
          // pin highlight, and saving a place shouldn't also select it.
          <button
            type="button"
            className={`favorite-button${isFavorite ? ' is-favorite' : ''}`}
            aria-pressed={isFavorite}
            aria-label={`${t(lang, isFavorite ? 'favoriteSaved' : 'favoriteSave')}: ${place.name}`}
            onClick={(e) => {
              e.stopPropagation()
              onToggleFavorite()
            }}
          >
            <Heart size={14} aria-hidden="true" fill={isFavorite ? 'currentColor' : 'none'} />
            {t(lang, isFavorite ? 'favoriteSaved' : 'favoriteSave')}
          </button>
        )}
        <a href={place.maps_url} target="_blank" rel="noopener noreferrer">
          <Navigation size={14} aria-hidden="true" />
          {t(lang, 'navigate')}
        </a>
        {place.instagram_url && (
          <a href={place.instagram_url} target="_blank" rel="noopener noreferrer">
            <Camera size={14} aria-hidden="true" />
            {t(lang, 'instagram')}
          </a>
        )}
        {place.id && reportStep === 'idle' && (
          <button
            type="button"
            className="report-button"
            aria-label={`${t(lang, 'reportPlace')}: ${place.name}`}
            title={t(lang, 'reportPlace')}
            onClick={(e) => {
              e.stopPropagation()
              setReportStep('choosing')
            }}
          >
            <MessageCircle size={14} aria-hidden="true" />
          </button>
        )}
      </div>
      {(reportStep === 'choosing' || reportStep === 'sending' || reportStep === 'failed') && (
        <div
          className="report-panel"
          role="group"
          aria-label={t(lang, 'reportPrompt')}
          onClick={(e) => e.stopPropagation()}
        >
          <p className="report-prompt">{t(lang, 'reportPrompt')}</p>
          <div className="report-options">
            <button type="button" disabled={reportStep === 'sending'} onClick={() => sendReport('would_return')}>
              {t(lang, 'reportWouldReturn')}
            </button>
            <button type="button" disabled={reportStep === 'sending'} onClick={() => sendReport('closed')}>
              {t(lang, 'reportClosed')}
            </button>
            <button type="button" disabled={reportStep === 'sending'} onClick={() => sendReport('wrong_category')}>
              {t(lang, 'reportWrongCategory')}
            </button>
            <button
              type="button"
              className="report-cancel"
              disabled={reportStep === 'sending'}
              onClick={() => setReportStep('idle')}
            >
              {t(lang, 'cancel')}
            </button>
          </div>
          {reportStep === 'failed' && (
            <p className="report-error" role="alert">
              {t(lang, 'reportFailed')}
            </p>
          )}
        </div>
      )}
      {reportStep === 'sent' && (
        <p className="report-thanks" role="status">
          {t(lang, sentKind === 'would_return' ? 'reportThanksWouldReturn' : 'reportThanks')}
        </p>
      )}
    </div>
  )
}
