import { CircleUserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { GoogleSignInButton } from './GoogleSignInButton'
import { t } from '../i18n'
import type { AuthUser, Lang, Theme } from '../types'

interface AccountControlProps {
  user: AuthUser | null
  googleClientId: string | null
  theme: Theme
  lang: Lang
  onCredential: (credential: string) => void
  onSignOut: () => void
}

// A menu, not a bare button - deliberately, so this same panel is where
// favorites/saved-spots get a home once those exist, instead of each new
// account-scoped feature fighting for its own header slot (see the header
// space concerns noted throughout this project). The trigger itself is
// always the same 44px icon-button regardless of auth state; only the
// panel's contents change.
export function AccountControl({ user, googleClientId, theme, lang, onCredential, onSignOut }: AccountControlProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isMenuOpen) return
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isMenuOpen])

  return (
    <div className="account-control" ref={containerRef}>
      <button
        type="button"
        className="account-avatar-button"
        onClick={() => setIsMenuOpen((open) => !open)}
        aria-label={t(lang, 'accountMenuLabel')}
        aria-expanded={isMenuOpen}
      >
        {user?.picture_url ? (
          <img src={user.picture_url} alt="" referrerPolicy="no-referrer" />
        ) : user ? (
          <span className="account-avatar-fallback">{user.name.charAt(0).toUpperCase()}</span>
        ) : (
          <CircleUserRound size={22} aria-hidden="true" />
        )}
      </button>
      {isMenuOpen && (
        <div className="account-menu" role="menu">
          <p className="account-menu-heading">{t(lang, 'accountHeading')}</p>
          {user ? (
            <>
              <p className="account-menu-name">
                {t(lang, 'signedInAsPrefix')} {user.name}
              </p>
              <button
                type="button"
                onClick={() => {
                  setIsMenuOpen(false)
                  onSignOut()
                }}
              >
                {t(lang, 'signOut')}
              </button>
            </>
          ) : (
            // Mounted only while the menu is open - a closed-then-reopened
            // panel always mounts this fresh, picking up whatever language/
            // theme is current at that moment rather than having to react
            // to a change while already mounted (see GoogleSignInButton -
            // reacting live to a language change means tearing down and
            // reloading Google's own script, which turned out to be a real
            // source of flaky rendering under rapid toggling).
            googleClientId && <GoogleSignInButton clientId={googleClientId} theme={theme} lang={lang} onCredential={onCredential} />
          )}
        </div>
      )}
    </div>
  )
}
