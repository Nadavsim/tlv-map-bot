// Deliberately does no caching - the app already relies on precise
// Cache-Control headers from the server (index.html always revalidated,
// hashed /static/assets/ cached forever; see backend/app.py's cache_control
// middleware), so a caching service worker would just duplicate that logic
// and risk serving stale content after a deploy. This exists solely to
// satisfy "installable PWA" checks that look for a registered service
// worker with a fetch handler - every request just passes straight through
// to the network.
self.addEventListener('fetch', () => {})
