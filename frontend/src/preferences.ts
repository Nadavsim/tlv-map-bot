import type { Lang, Theme } from './types'

const LANG_KEY = 'tlv-bot-lang'
const THEME_KEY = 'tlv-bot-theme'
const INTRO_SEEN_KEY = 'tlv-bot-intro-seen'

// Wrapped in try/catch since localStorage can throw (private browsing mode
// in some browsers, site data blocked) - a missing preference should just
// fall back to a default, never break the app.

export function loadLang(): Lang {
  try {
    const stored = localStorage.getItem(LANG_KEY)
    if (stored === 'en' || stored === 'he') return stored
  } catch {
    // fall through to default
  }
  return 'en'
}

export function saveLang(lang: Lang): void {
  try {
    localStorage.setItem(LANG_KEY, lang)
  } catch {
    // not persisted this session - not worth surfacing to the user
  }
}

// Whether this browser has already used the app (sent a message or opened
// Help) - the one-time first-visit prompt only shows until then. Falls back
// to "not seen" when storage is unavailable, so a visitor with blocked
// storage sees it each visit rather than never.
export function loadIntroSeen(): boolean {
  try {
    return localStorage.getItem(INTRO_SEEN_KEY) === '1'
  } catch {
    return false
  }
}

export function saveIntroSeen(): void {
  try {
    localStorage.setItem(INTRO_SEEN_KEY, '1')
  } catch {
    // not persisted - the prompt just shows again next visit
  }
}

export function loadTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    // fall through to the system preference
  }
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    // not persisted this session - not worth surfacing to the user
  }
}
