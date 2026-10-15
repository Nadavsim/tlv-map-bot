import { ChevronDown, ChevronUp, HeartOff, MapPin, Navigation } from 'lucide-react'
import { useState } from 'react'
import { GoogleSignInButton } from './GoogleSignInButton'
import { t } from '../i18n'
import type { AuthUser, Lang, Place, SavedAddress, Theme } from '../types'

interface AccountSectionProps {
  isOpen: boolean
  user: AuthUser | null
  googleClientId: string | null
  theme: Theme
  lang: Lang
  onCredential: (credential: string) => void
  onSignOut: () => void
  savedAddresses: SavedAddress[]
  onUseSavedAddress: (address: SavedAddress) => void
  onRemoveSavedAddress: (id: string) => void
  // Resolves true once the account is gone (the caller closes the menu),
  // false if it couldn't be deleted - the account is then left untouched.
  onDeleteAccount: () => Promise<boolean>
  favorites: Place[]
  // Shows them as result cards in the chat, nearest first.
  onShowFavorites: () => void
  onRemoveFavorite: (place: Place) => void
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
  onUseSavedAddress,
  onRemoveSavedAddress,
  onDeleteAccount,
  favorites,
  onShowFavorites,
  onRemoveFavorite,
}: AccountSectionProps) {
  // Deleting is two deliberate steps (button -> explicit confirmation), and
  // never one tap away from the sign-out button sitting right above it.
  const [deleteStep, setDeleteStep] = useState<'idle' | 'confirm' | 'deleting' | 'failed'>('idle')
  // The saved list is collapsed until asked for - it is a management corner of
  // the menu, not something to read every time it opens. One row at a time
  // shows its actions (an accordion), so the list never turns into a wall of
  // buttons.
  const [listOpen, setListOpen] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)
  // Same idea for favorites: collapsed until asked for. A row is a navigation
  // link (one tap), so there's no per-row accordion here.
  const [favoritesOpen, setFavoritesOpen] = useState(false)

  async function handleConfirmDelete() {
    setDeleteStep('deleting')
    const ok = await onDeleteAccount()
    // On success the account (and this whole section's signed-in view) is
    // gone; only a failure needs to leave the confirmation visible.
    setDeleteStep(ok ? 'idle' : 'failed')
  }

  function toggleList() {
    setListOpen((open) => !open)
    setActiveId(null)
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
            {favorites.length === 0 ? (
              <>
                <p className="account-section-heading">{t(lang, 'favoritesHeading')}</p>
                <p className="saved-addresses-note">{t(lang, 'favoritesEmpty')}</p>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="saved-addresses-toggle"
                  aria-expanded={favoritesOpen}
                  aria-controls="favorites-list"
                  onClick={() => setFavoritesOpen((open) => !open)}
                >
                  <span>
                    {t(lang, 'favoritesHeading')} ({favorites.length})
                  </span>
                  {favoritesOpen ? (
                    <ChevronUp size={16} aria-hidden="true" />
                  ) : (
                    <ChevronDown size={16} aria-hidden="true" />
                  )}
                </button>
                {favoritesOpen && (
                  <>
                    <ul className="saved-addresses-list" id="favorites-list">
                      {[...favorites]
                        .sort((a, b) => a.name.localeCompare(b.name, lang))
                        .map((place) => (
                          <li key={place.id ?? place.maps_url} className="favorites-row">
                            <a
                              className="saved-addresses-row favorites-link"
                              href={place.maps_url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <Navigation size={14} aria-hidden="true" />
                              <span className="saved-addresses-label">{place.name}</span>
                              <span className="favorites-category">{place.category}</span>
                            </a>
                            <button
                              type="button"
                              className="favorites-remove"
                              aria-label={`${t(lang, 'favoriteRemove')}: ${place.name}`}
                              title={t(lang, 'favoriteRemove')}
                              onClick={() => onRemoveFavorite(place)}
                            >
                              <HeartOff size={16} aria-hidden="true" />
                            </button>
                          </li>
                        ))}
                    </ul>
                    <button type="button" className="favorites-show-in-chat" onClick={onShowFavorites}>
                      {t(lang, 'favoritesShowInChat')}
                    </button>
                  </>
                )}
              </>
            )}
          </div>

          <div className="saved-addresses">
            {savedAddresses.length === 0 ? (
              <>
                <p className="account-section-heading">{t(lang, 'savedAddressesHeading')}</p>
                <p className="saved-addresses-note">{t(lang, 'savedAddressesEmpty')}</p>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="saved-addresses-toggle"
                  aria-expanded={listOpen}
                  aria-controls="saved-addresses-list"
                  onClick={toggleList}
                >
                  <span>
                    {t(lang, 'savedAddressesHeading')} ({savedAddresses.length})
                  </span>
                  {listOpen ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
                </button>
                {listOpen && (
                  <>
                    <ul className="saved-addresses-list" id="saved-addresses-list">
                      {savedAddresses.map((address) => {
                        const isActive = activeId === address.id
                        return (
                          <li key={address.id}>
                            <button
                              type="button"
                              className={`saved-addresses-row${isActive ? ' active' : ''}`}
                              aria-expanded={isActive}
                              onClick={() => setActiveId(isActive ? null : address.id)}
                            >
                              <MapPin size={14} aria-hidden="true" />
                              <span className="saved-addresses-label">{address.label}</span>
                            </button>
                            {isActive && (
                              <div className="saved-addresses-actions">
                                <button
                                  type="button"
                                  className="saved-addresses-use"
                                  onClick={() => onUseSavedAddress(address)}
                                >
                                  {t(lang, 'useSavedAddress')}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setActiveId(null)
                                    onRemoveSavedAddress(address.id)
                                  }}
                                >
                                  {t(lang, 'removeSavedAddress')}
                                </button>
                              </div>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                    <p className="saved-addresses-note">{t(lang, 'savedAddressesHint')}</p>
                  </>
                )}
              </>
            )}
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
