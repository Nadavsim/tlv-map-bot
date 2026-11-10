import { useEffect, useRef } from 'react'
import type { Lang, Theme } from '../types'

// Google Identity Services isn't published as an official npm package (and
// this project avoids adding dependencies where a plain script tag does the
// job - same reasoning as the hand-rolled i18n) - just enough of its shape
// to type the handful of calls this component makes.
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(config: { client_id: string; callback: (response: { credential: string }) => void }): void
          renderButton(
            parent: HTMLElement,
            options: {
              theme: 'outline' | 'filled_black'
              shape: 'pill'
              size: 'large'
              text: 'signin_with'
              width: number
              locale: Lang
            },
          ): void
        }
      }
    }
  }
}

const SCRIPT_ID = 'google-identity-services'

// Google warns (and uses only the last call) when initialize() runs more than
// once per script load, so it is done once per client id; reset whenever the
// script is replaced, since a fresh script has no memory of it.
let initializedClientId: string | null = null

interface GoogleSignInButtonProps {
  clientId: string
  theme: Theme
  lang: Lang
  onCredential: (credential: string) => void
}

export function GoogleSignInButton({ clientId, theme, lang, onCredential }: GoogleSignInButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  // The parent hands in a new function on every render. Reading it through a ref
  // keeps it out of the effect's dependencies - otherwise every re-render of the
  // app tore the button down and rebuilt it (a visible flicker), and a sign-in
  // that completed mid-rebuild could call a stale handler.
  const onCredentialRef = useRef(onCredential)
  useEffect(() => {
    onCredentialRef.current = onCredential
  })

  useEffect(() => {
    function render() {
      if (!containerRef.current || !window.google) return
      if (initializedClientId !== clientId) {
        window.google.accounts.id.initialize({ client_id: clientId, callback: (response) => onCredentialRef.current(response.credential) })
        initializedClientId = clientId
      }
      containerRef.current.innerHTML = ''
      // The full branded "Sign in with Google" button - safe to use here
      // since this only ever renders inside the account menu panel, which
      // has real room, unlike the header's own 44px icon row (an earlier
      // version tried putting this same full button directly in the
      // header and it overflowed at mobile widths).
      window.google.accounts.id.renderButton(containerRef.current, {
        theme: theme === 'dark' ? 'filled_black' : 'outline',
        shape: 'pill',
        size: 'large',
        text: 'signin_with',
        width: 220,
        // Without this Google picks the language itself (the visitor's Google
        // account or browser) and swaps the button to it a moment after it first
        // appears, ignoring this app's own language toggle.
        locale: lang,
      })
    }

    // Google decides the button's language in two places, and they must agree or
    // the button flips between them: the script URL's `hl` (what it shows first)
    // and renderButton's `locale` above (what it settles on). A language change
    // therefore needs a fresh script load, not just a re-render. That is safe
    // here because this component only exists while the menu is open, and
    // changing the language closes the menu, so no button is alive to flicker.
    const scriptUrl = `https://accounts.google.com/gsi/client?hl=${lang}`
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null
    if (existing) {
      if (existing.src === scriptUrl) {
        if (window.google) {
          render()
        } else {
          // Still loading from an earlier mount: render when it arrives. Removed
          // on cleanup so a stale handler can't draw an out-of-date language.
          existing.addEventListener('load', render, { once: true })
          return () => existing.removeEventListener('load', render)
        }
        return
      }
      existing.remove()
      window.google = undefined
      initializedClientId = null
    }

    const script = document.createElement('script')
    script.id = SCRIPT_ID
    script.src = scriptUrl
    script.async = true
    script.defer = true
    script.addEventListener('load', render, { once: true })
    document.body.appendChild(script)
    return () => script.removeEventListener('load', render)
  }, [clientId, theme, lang])

  return <div ref={containerRef} className="google-signin-button" />
}
