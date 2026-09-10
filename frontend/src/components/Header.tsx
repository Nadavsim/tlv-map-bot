import { Car, CircleHelp, Footprints, Languages, MapPin, Moon, RotateCcw, Sun } from 'lucide-react'
import { t } from '../i18n'
import type { Lang, Theme, TransportMode } from '../types'

interface HeaderProps {
  locationStatus: string
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
      <p className="location-status">{locationStatus}</p>
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
