import { Car, Footprints, LocateFixed, MapPin, Menu } from 'lucide-react'
import { useState } from 'react'
import { SideMenu } from './SideMenu'
import { t } from '../i18n'
import type { AuthUser, Lang, LocationMode, Theme, TransportMode } from '../types'

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
  authUser: AuthUser | null
  googleClientId: string | null
  onGoogleCredential: (credential: string) => void
  onSignOut: () => void
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
  authUser,
  googleClientId,
  onGoogleCredential,
  onSignOut,
}: HeaderProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false)

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
            onClick={() => setIsMenuOpen(true)}
            aria-label={t(lang, 'menuLabel')}
          >
            <Menu size={20} aria-hidden="true" />
          </button>
        </div>
      </div>
      <SideMenu
        isOpen={isMenuOpen}
        onClose={() => setIsMenuOpen(false)}
        lang={lang}
        onLangChange={onLangChange}
        theme={theme}
        onThemeChange={onThemeChange}
        onHelp={onHelp}
        onNewConversation={onNewConversation}
        authUser={authUser}
        googleClientId={googleClientId}
        onGoogleCredential={onGoogleCredential}
        onSignOut={onSignOut}
      />
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
