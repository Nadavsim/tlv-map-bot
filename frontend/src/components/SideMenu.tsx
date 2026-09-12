import { CircleHelp, Languages, Moon, RotateCcw, Sun, X } from 'lucide-react'
import { useEffect } from 'react'
import { AccountSection } from './AccountSection'
import { t } from '../i18n'
import type { AuthUser, Lang, Theme } from '../types'

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
          <button type="button" className="side-menu-close" onClick={onClose} aria-label={t(lang, 'closeMenu')}>
            <X size={22} aria-hidden="true" />
          </button>
        </div>
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
        <AccountSection
          isOpen={isOpen}
          user={authUser}
          googleClientId={googleClientId}
          theme={theme}
          lang={lang}
          onCredential={onGoogleCredential}
          onSignOut={() => selectAndClose(onSignOut)}
        />
      </div>
    </>
  )
}
