import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// A no-op service worker (see public/sw.js) - it does no caching, it just
// needs to exist and be registered for Chrome/Android to consider the app
// installable as a PWA. Registration failing (old browser, restrictive
// proxy) should never be user-visible - it's a progressive enhancement.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}
