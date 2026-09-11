import { Component, type ErrorInfo, type ReactNode } from 'react'
import { t } from '../i18n'
import { loadLang } from '../preferences'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

// Class component is required here - React only exposes error-boundary
// behavior via componentDidCatch/getDerivedStateFromError, there's no hook
// equivalent. Reads the language preference directly (not from App's own
// state) since this exists specifically to catch a crash *inside* App - it
// can't assume anything about App's current state is still trustworthy.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      const lang = loadLang()
      return (
        <div className="error-boundary">
          <p>{t(lang, 'appCrashedMessage')}</p>
          <button type="button" onClick={() => window.location.reload()}>
            {t(lang, 'appCrashedReload')}
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
