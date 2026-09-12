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

  if (!user) {
    // Config hasn't loaded yet (a single fetch on app start) - render
    // nothing rather than a half-configured button for that brief window.
    if (!googleClientId) return null
    return <GoogleSignInButton clientId={googleClientId} theme={theme} lang={lang} onCredential={onCredential} />
  }

  return (
    <div className="account-control" ref={containerRef}>
      <button
        type="button"
        className="account-avatar-button"
        onClick={() => setIsMenuOpen((open) => !open)}
        aria-label={t(lang, 'accountMenuLabel')}
        aria-expanded={isMenuOpen}
      >
        {user.picture_url ? (
          <img src={user.picture_url} alt="" referrerPolicy="no-referrer" />
        ) : (
          <span className="account-avatar-fallback">{user.name.charAt(0).toUpperCase()}</span>
        )}
      </button>
      {isMenuOpen && (
        <div className="account-menu" role="menu">
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
        </div>
      )}
    </div>
  )
}
