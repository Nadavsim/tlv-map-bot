// Lets the standalone pages (About, Privacy, 404) follow the theme the visitor
// picked in the app, instead of only the phone's own light/dark setting.
// Same origin as the app, so it can read the app's saved choice. Runs in
// <head> before the page paints so there is no flash of the wrong theme. With
// no saved choice (or blocked storage) nothing is set and the CSS falls back
// to the OS preference, exactly as before.
try {
  var saved = localStorage.getItem('tlv-bot-theme')
  if (saved === 'light' || saved === 'dark') {
    document.documentElement.setAttribute('data-theme', saved)
  }
} catch (e) {
  // Storage can throw (private mode, blocked site data) - the OS default is fine.
}
