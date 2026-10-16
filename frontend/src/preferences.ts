import type { Lang, Theme } from './types'

const LANG_KEY = 'tlv-bot-lang'
const THEME_KEY = 'tlv-bot-theme'

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
