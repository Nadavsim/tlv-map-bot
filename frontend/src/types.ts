export type TransportMode = 'walking' | 'driving'
export type Lang = 'en' | 'he'
export type Theme = 'light' | 'dark'
// 'live' uses the browser's geolocation fix; 'manual' overrides it with a
// user-typed address/Maps link/coordinates, independent of whether live
// geolocation is working - lets a user plan ahead for a different spot.
export type LocationMode = 'live' | 'manual'

export interface ChatRequest {
  message: string
  lat: number
  lon: number
  lang: Lang
  // Just enough of the previous turn for the backend/LLM to recognize a
  // refinement ("something else", "another one") - see App.tsx's
  // getPreviousContext. previousCategory=null with hasPreviousContext=true
  // means the previous turn was "any category" (surprise me), not "no
  // previous turn at all".
  previous_category: string | null
  previous_dietary_tag: string | null
  previous_price_tier: PriceTier | null
  previous_offset: number
  has_previous_context: boolean
}

export type PriceTier = '$' | '$$' | '$$$'

export interface Place {
  // The place's stable id (what a favorite points at). Always present from
  // the API; optional only so a card never breaks if one is missing.
  id?: string | null
  name: string
  category: string
  distance: string
  // Always null as it arrives from /api/chat and /api/more-places: travel
  // times come from a separate request (see App.tsx requestEtas) so a slow
  // routing service can't hold up the results.
  eta: string | null
  // Client-side only: true from the moment the place is shown until its ETA
  // request has answered (successfully or not).
  etaPending?: boolean
  instagram_url: string | null
  dietary_tags: string[]
  price_tier: PriceTier | null
  closes_at_hour: number | null
  outdoor_seating: boolean
  maps_url: string
  lat: number
  lon: number
}

export interface ChatResponse {
  reply: string
  places: Place[]
  category: string | null
  dietary_tag: string | null
  price_tier: PriceTier | null
  offset: number
}

export interface MorePlacesRequest {
  category: string | null
  tag: string | null
  price: PriceTier | null
  lat: number
  lon: number
  offset: number
}

export interface EtasRequest {
  mode: TransportMode
  lat: number
  lon: number
  destinations: { lat: number; lon: number }[]
}

export interface EtasResponse {
  // Aligned with the request's destinations; null = no ETA available.
  etas: (string | null)[]
}

export interface MorePlacesResponse {
  places: Place[]
}

export interface ResolveLocationResponse {
  lat: number | null
  lon: number | null
  // For a pasted link: the place's own name/address, shown in place of the
  // long URL. Absent for typed text, which is its own label.
  label?: string | null
  // Set instead of lat/lon when the typed text found nothing but a corrected
  // spelling does: offered to the person, never applied on its own.
  suggestion?: { text: string; lat: number; lon: number } | null
}

export interface CategoriesResponse {
  categories: string[]
}

// Matches backend.app.PAGE_SIZE - a page shorter than this means there's
// nothing left to fetch, so "Show more" hides itself.
export const PAGE_SIZE = 3

export interface Coordinates {
  lat: number
  lon: number
}

export interface AuthUser {
  name: string
  email: string
  picture_url: string | null
}

export interface SavedAddress {
  id: string
  // The address text the person typed (or coordinates, if they typed a link) -
  // never a name like "Home"; the backend has no such field.
  label: string
  lat: number
  lon: number
}

export interface SavedAddressesResponse {
  addresses: SavedAddress[]
  max: number
}

export interface FavoriteIdsResponse {
  ids: string[]
  max: number
}

export interface FavoritePlacesResponse {
  places: Place[]
}

export interface AuthResponse {
  access_token: string
  user: AuthUser
}

export interface AuthConfigResponse {
  google_client_id: string
}
