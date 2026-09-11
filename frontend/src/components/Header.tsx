import { Car, CircleHelp, Footprints, Languages, LocateFixed, MapPin, Moon, RotateCcw, Sun } from 'lucide-react'
import { t } from '../i18n'
import type { Lang, LocationMode, Theme, TransportMode } from '../types'

interface HeaderProps {
  locationStatus: string
  locationMode: LocationMode
  onLocationModeChange: (mode: LocationMode) => void
  canChangeManualLocation: boolean
  onChangeManualLocation: () => void
  mode: TransportMode
  onModeChange: (mode: TransportMode) => void
  onHelp: () => void
  onNewConversation: () => void
  lang: Lang
  onLangChange: (lang: Lang) => void
  theme: Theme
  onThemeChange: (theme: Theme) => void
}

export function Header({
  locationStatus,
  locationMode,
  onLocationModeChange,
  canChangeManualLocation,
  onChangeManualLocation,
  mode,
  onModeChange,
  onHelp,
  onNewConversation,
  lang,
  onLangChange,
  theme,
  onThemeChange,
}: HeaderProps) {
  return (
    <header>
      <div className="header-top">
        <h1>
          <MapPin size={22} aria-hidden="true" />
          TLV Bot
        </h1>
        <div className="header-actions">
          <button
            type="button"
            className="icon-button"
            onClick={() => onLangChange(lang === 'en' ? 'he' : 'en')}
            aria-label={t(lang, 'languageToggle')}
          >
            <Languages size={18} aria-hidden="true" />
            <span>{t(lang, 'languageToggle')}</span>
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={() => onThemeChange(theme === 'light' ? 'dark' : 'light')}
            aria-label={theme === 'light' ? t(lang, 'themeToggleToDark') : t(lang, 'themeToggleToLight')}
            title={theme === 'light' ? t(lang, 'themeToggleToDark') : t(lang, 'themeToggleToLight')}
          >
            {theme === 'light' ? <Moon size={18} aria-hidden="true" /> : <Sun size={18} aria-hidden="true" />}
          </button>
          <button type="button" className="icon-button" onClick={onNewConversation} aria-label={t(lang, 'newConversation')}>
            <RotateCcw size={18} aria-hidden="true" />
            <span>{t(lang, 'newConversation')}</span>
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={onHelp}
            aria-label={t(lang, 'help')}
            title={t(lang, 'help')}
          >
            <CircleHelp size={20} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="location-status-row">
        <p className="location-status">{locationStatus}</p>
        {canChangeManualLocation && (
          <button type="button" className="change-location-button" onClick={onChangeManualLocation}>
            {t(lang, 'locationChangeButton')}
          </button>
        )}
      </div>
      <div className="mode-toggle" role="group" aria-label={t(lang, 'locationModeGroupLabel')}>
        <button
          type="button"
          className={locationMode === 'manual' ? 'active' : ''}
          onClick={() => onLocationModeChange('manual')}
        >
          <MapPin size={16} aria-hidden="true" />
          {t(lang, 'locationModeCustom')}
        </button>
        <button
          type="button"
          className={locationMode === 'live' ? 'active' : ''}
          onClick={() => onLocationModeChange('live')}
        >
          <LocateFixed size={16} aria-hidden="true" />
          {t(lang, 'locationModeLive')}
        </button>
      </div>
      <div className="mode-toggle" role="group" aria-label={t(lang, 'transportMode')}>
        <button
          type="button"
          className={mode === 'walking' ? 'active' : ''}
          onClick={() => onModeChange('walking')}
        >
          <Footprints size={16} aria-hidden="true" />
          {t(lang, 'walk')}
        </button>
        <button
          type="button"
          className={mode === 'driving' ? 'active' : ''}
          onClick={() => onModeChange('driving')}
        >
          <Car size={16} aria-hidden="true" />
          {t(lang, 'drive')}
        </button>
      </div>
    </header>
  )
}
