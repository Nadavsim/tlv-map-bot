import { CircleHelp, Info, Languages, Moon, RotateCcw, ShieldCheck, Sun, X } from 'lucide-react'
import { useEffect } from 'react'
import { AccountSection } from './AccountSection'
import { t } from '../i18n'
import type { AuthUser, Lang, Place, SavedAddress, SuggestOutcome, Theme } from '../types'

interface SideMenuProps {
  isOpen: boolean
  onClose: () => void
  lang: Lang
  onLangChange: (lang: Lang) => void
  theme: Theme
  onThemeChange: (theme: Theme) => void
  onHelp: () => void
  onNewConversation: () => void
  authUser: AuthUser | null
  googleClientId: string | null
  onGoogleCredential: (credential: string) => void
  onSignOut: () => void
  savedAddresses: SavedAddress[]
  onUseSavedAddress: (address: SavedAddress) => void
  onRemoveSavedAddress: (id: string) => void
  onDeleteAccount: () => Promise<boolean>
  favorites: Place[]
  onShowFavorites: () => void
  onRemoveFavorite: (place: Place) => void
  onSuggestSpot: (place: string, category: string) => Promise<SuggestOutcome>
}

// The header's old icon row (language/theme/reset/help, plus the account
// icon before that) stopped fitting on narrow phones once it had 5 controls
// - a real, live-reported overflow, not a hypothetical one. Consolidating
// them into a slide-out drawer is the standard fix most sites reach for
// here, and conveniently gives the account section (and anything
// account-scoped that comes after it - favorites, saved spots) a spacious,
// permanent home instead of fighting for header space.
export function SideMenu({
  isOpen,
  onClose,
  lang,
  onLangChange,
  theme,
  onThemeChange,
  onHelp,
  onNewConversation,
  authUser,
  googleClientId,
  onGoogleCredential,
  onSignOut,
  savedAddresses,
  onUseSavedAddress,
  onRemoveSavedAddress,
  onDeleteAccount,
  favorites,
  onShowFavorites,
  onRemoveFavorite,
  onSuggestSpot,
}: SideMenuProps) {
  useEffect(() => {
    if (!isOpen) return
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isOpen, onClose])

  function selectAndClose(action: () => void) {
    action()
    onClose()
  }

  return (
    <>
      <div className={`side-menu-backdrop ${isOpen ? 'open' : ''}`} onClick={onClose} aria-hidden="true" />
      <div className={`side-menu ${isOpen ? 'open' : ''}`} role="dialog" aria-modal="true" aria-label={t(lang, 'menuLabel')} inert={!isOpen}>
        <div className="side-menu-top">
          <span className="side-menu-wordmark">TLV Bot</span>
          <button type="button" className="side-menu-close" onClick={onClose} aria-label={t(lang, 'closeMenu')}>
            <X size={22} aria-hidden="true" />
          </button>
        </div>
        <p className="side-menu-curator">{t(lang, 'drawerCurator')}</p>
        <AccountSection
          isOpen={isOpen}
          user={authUser}
          googleClientId={googleClientId}
          theme={theme}
          lang={lang}
          onCredential={onGoogleCredential}
          onSignOut={() => selectAndClose(onSignOut)}
          savedAddresses={savedAddresses}
          onUseSavedAddress={(address) => selectAndClose(() => onUseSavedAddress(address))}
          onRemoveSavedAddress={onRemoveSavedAddress}
          favorites={favorites}
          onShowFavorites={() => selectAndClose(onShowFavorites)}
          onRemoveFavorite={onRemoveFavorite}
          onSuggestSpot={onSuggestSpot}
          onDeleteAccount={async () => {
            const ok = await onDeleteAccount()
            if (ok) onClose()
            return ok
          }}
        />
        <div className="side-menu-bottom">
          <p className="account-section-heading">{t(lang, 'settingsHeading')}</p>
          <div className="side-menu-items">
            <button
              type="button"
              className="side-menu-item"
              onClick={() => selectAndClose(() => onLangChange(lang === 'en' ? 'he' : 'en'))}
            >
              <Languages size={18} aria-hidden="true" />
              {t(lang, 'languageToggle')}
            </button>
            <button
              type="button"
              className="side-menu-item"
              onClick={() => selectAndClose(() => onThemeChange(theme === 'light' ? 'dark' : 'light'))}
            >
              {theme === 'light' ? <Moon size={18} aria-hidden="true" /> : <Sun size={18} aria-hidden="true" />}
              {theme === 'light' ? t(lang, 'themeToggleToDark') : t(lang, 'themeToggleToLight')}
            </button>
            <button type="button" className="side-menu-item" onClick={() => selectAndClose(onNewConversation)}>
              <RotateCcw size={18} aria-hidden="true" />
              {t(lang, 'newConversation')}
            </button>
            <button type="button" className="side-menu-item" onClick={() => selectAndClose(onHelp)}>
              <CircleHelp size={18} aria-hidden="true" />
              {t(lang, 'help')}
            </button>
          </div>
          <div className="side-menu-items side-menu-links">
            <a className="side-menu-item" href="/about" target="_blank" rel="noopener noreferrer">
              <Info size={18} aria-hidden="true" />
              {t(lang, 'aboutLink')}
            </a>
            <a className="side-menu-item" href="/privacy" target="_blank" rel="noopener noreferrer">
              <ShieldCheck size={18} aria-hidden="true" />
              {t(lang, 'privacyLink')}
            </a>
          </div>
        </div>
      </div>
    </>
  )
}
