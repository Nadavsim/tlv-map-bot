import { Component, type ErrorInfo, type ReactNode } from 'react'
import { t } from '../i18n'
import type { Lang } from '../types'

interface Props {
  lang: Lang
  children: ReactNode
}

// Scoped to the map only. The lazy chunk can fail to load (offline, or a
// deploy replaced its hashed filename mid-session) - without this, that
// rejection would bubble to the app-wide ErrorBoundary and replace the whole
// chat with the crash screen, over an optional extra.
export class MapErrorBoundary extends Component<Props, { hasError: boolean }> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Map failed to load:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="map-view map-placeholder" role="alert">
          {t(this.props.lang, 'mapLoadError')}
        </div>
      )
    }
    return this.props.children
  }
}
