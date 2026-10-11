import { MapPin, X } from 'lucide-react'
import { useState } from 'react'
import { GoogleSignInButton } from './GoogleSignInButton'
import { t } from '../i18n'
import type { AuthUser, Lang, SavedAddress, Theme } from '../types'

interface AccountSectionProps {
  isOpen: boolean
  user: AuthUser | null
  googleClientId: string | null
  theme: Theme
  lang: Lang
  onCredential: (credential: string) => void
  onSignOut: () => void
  savedAddresses: SavedAddress[]
  onRemoveSavedAddress: (id: string) => void
  // Resolves true once the account is gone (the caller closes the menu),
  // false if it couldn't be deleted - the account is then left untouched.
  onDeleteAccount: () => Promise<boolean>
}

// Pure content, no trigger/popover of its own - lives pinned to the bottom
// of SideMenu. `isOpen` gates the Google button specifically (not just this
// component's own mount) so it only ever mounts while the menu is actually
// open - see GoogleSignInButton for why that matters (reacting to a
// language change while it stayed mounted turned out to be genuinely flaky
// under rapid toggling; mounting fresh each time the menu opens sidesteps
// that instead of reacting to it live).
export function AccountSection({
  isOpen,
  user,
  googleClientId,
  theme,
  lang,
  onCredential,
  onSignOut,
  savedAddresses,
  onRemoveSavedAddress,
  onDeleteAccount,
}: AccountSectionProps) {
  // Deleting is two deliberate steps (button -> explicit confirmation), and
  // never one tap away from the sign-out button sitting right above it.
  const [deleteStep, setDeleteStep] = useState<'idle' | 'confirm' | 'deleting' | 'failed'>('idle')

  async function handleConfirmDelete() {
    setDeleteStep('deleting')
    const ok = await onDeleteAccount()
    // On success the account (and this whole section's signed-in view) is
    // gone; only a failure needs to leave the confirmation visible.
    setDeleteStep(ok ? 'idle' : 'failed')
  }

  return (
    <div className="account-section">
      <p className="account-section-heading">{t(lang, 'accountHeading')}</p>
      {user ? (
        <>
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

          <div className="saved-addresses">
            <p className="account-section-heading">{t(lang, 'savedAddressesHeading')}</p>
            {savedAddresses.length === 0 ? (
              <p className="saved-addresses-note">{t(lang, 'savedAddressesEmpty')}</p>
            ) : (
              <ul className="saved-addresses-list">
                {savedAddresses.map((address) => (
                  <li key={address.id}>
                    <MapPin size={14} aria-hidden="true" />
                    <span className="saved-addresses-label" dir="auto">
                      {address.label}
                    </span>
                    <button
                      type="button"
                      className="saved-addresses-remove"
                      onClick={() => onRemoveSavedAddress(address.id)}
                      aria-label={`${t(lang, 'removeSavedAddress')}: ${address.label}`}
                    >
                      <X size={16} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="saved-addresses-note">{t(lang, 'savedAddressesHint')}</p>
          </div>

          <div className="delete-account">
            {deleteStep === 'idle' ? (
              <button type="button" className="delete-account-link" onClick={() => setDeleteStep('confirm')}>
                {t(lang, 'deleteAccount')}
              </button>
            ) : (
              <div className="delete-account-confirm" role="alertdialog" aria-label={t(lang, 'deleteAccount')}>
                <p>{t(lang, 'deleteAccountWarning')}</p>
                {deleteStep === 'failed' && (
                  <p className="delete-account-error" role="alert">
                    {t(lang, 'deleteAccountFailed')}
                  </p>
                )}
                <div className="delete-account-actions">
                  <button
                    type="button"
                    className="delete-account-danger"
                    disabled={deleteStep === 'deleting'}
                    onClick={handleConfirmDelete}
                  >
                    {deleteStep === 'deleting' ? t(lang, 'deletingAccount') : t(lang, 'deleteAccountConfirm')}
                  </button>
                  <button
                    type="button"
                    disabled={deleteStep === 'deleting'}
                    onClick={() => setDeleteStep('idle')}
                  >
                    {t(lang, 'cancel')}
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      ) : (
        isOpen && googleClientId && (
          <GoogleSignInButton clientId={googleClientId} theme={theme} lang={lang} onCredential={onCredential} />
        )
      )}
    </div>
  )
}
