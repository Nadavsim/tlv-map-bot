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
            options: { theme: 'outline' | 'filled_black'; type: 'icon'; shape: 'circle'; size: 'medium' },
          ): void
        }
      }
    }
  }
}

const SCRIPT_ID = 'google-identity-services'

interface GoogleSignInButtonProps {
  clientId: string
  theme: Theme
  lang: Lang
  onCredential: (credential: string) => void
}

export function GoogleSignInButton({ clientId, theme, lang, onCredential }: GoogleSignInButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function render() {
      if (!containerRef.current || !window.google) return
      // initialize() is safe to call again on a theme/language change - it
      // just re-registers the same callback, it doesn't create a second
      // listener.
      window.google.accounts.id.initialize({ client_id: clientId, callback: (response) => onCredential(response.credential) })
      containerRef.current.innerHTML = ''
      // Icon-only (not the full "Sign in with Google" text button) - this
      // sits in the header's icon row alongside 44px touch targets, not as
      // a wide standalone CTA; the full-text variant overflowed that row on
      // narrow phones once added to the existing 4 controls.
      window.google.accounts.id.renderButton(containerRef.current, {
        theme: theme === 'dark' ? 'filled_black' : 'outline',
        type: 'icon',
        shape: 'circle',
        size: 'medium',
      })
    }

    // The button's own text is baked into the script Google serves, keyed
    // by this `hl` query param - without it, Google falls back to the
    // browser's own locale/an existing Google session's language, which can
    // silently mismatch this app's own (independent) language toggle. A
    // language change needs a fresh script load, not just a re-render.
    const scriptUrl = `https://accounts.google.com/gsi/client?hl=${lang}`
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null
    if (existing) {
      if (existing.src === scriptUrl && window.google) {
        render()
        return
      }
      existing.remove()
      window.google = undefined
    }

    const script = document.createElement('script')
    script.id = SCRIPT_ID
    script.src = scriptUrl
    script.async = true
    script.defer = true
    script.addEventListener('load', render, { once: true })
    document.body.appendChild(script)
  }, [clientId, theme, lang, onCredential])

  return <div ref={containerRef} className="google-signin-button" />
}
