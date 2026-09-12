import { GoogleSignInButton } from './GoogleSignInButton'
import { t } from '../i18n'
import type { AuthUser, Lang, Theme } from '../types'

interface AccountSectionProps {
  isOpen: boolean
  user: AuthUser | null
  googleClientId: string | null
  theme: Theme
  lang: Lang
  onCredential: (credential: string) => void
  onSignOut: () => void
}

// Pure content, no trigger/popover of its own - lives pinned to the bottom
// of SideMenu. `isOpen` gates the Google button specifically (not just this
// component's own mount) so it only ever mounts while the menu is actually
// open - see GoogleSignInButton for why that matters (reacting to a
// language change while it stayed mounted turned out to be genuinely flaky
// under rapid toggling; mounting fresh each time the menu opens sidesteps
// that instead of reacting to it live).
export function AccountSection({ isOpen, user, googleClientId, theme, lang, onCredential, onSignOut }: AccountSectionProps) {
  return (
    <div className="account-section">
      <p className="account-section-heading">{t(lang, 'accountHeading')}</p>
      {user ? (
        <div className="account-section-signed-in">
          {user.picture_url ? (
            <img src={user.picture_url} alt="" referrerPolicy="no-referrer" className="account-avatar-image" />
          ) : (
            <span className="account-avatar-fallback">{user.name.charAt(0).toUpperCase()}</span>
          )}
          <div className="account-section-info">
            <p className="account-section-name">{user.name}</p>
            <button type="button" onClick={onSignOut}>
              {t(lang, 'signOut')}
            </button>
          </div>
        </div>
      ) : (
        isOpen && googleClientId && (
          <GoogleSignInButton clientId={googleClientId} theme={theme} lang={lang} onCredential={onCredential} />
        )
      )}
    </div>
  )
}
