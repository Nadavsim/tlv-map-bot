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
  mode: TransportMode
  lang: Lang
  // Just enough of the previous turn for the backend/LLM to recognize a
  // refinement ("something else", "another one") - see App.tsx's
  // getPreviousContext. previousCategory=null with hasPreviousContext=true
  // means the previous turn was "any category" (surprise me), not "no
  // previous turn at all".
  previous_category: string | null
  previous_dietary_tag: string | null
  previous_offset: number
  has_previous_context: boolean
}

export interface Place {
  name: string
  category: string
  distance: string
  eta: string | null
  instagram_url: string | null
  dietary_tags: string[]
  price_tier: '$' | '$$' | '$$$' | null
  maps_url: string
}

export interface ChatResponse {
  reply: string
  places: Place[]
  category: string | null
  dietary_tag: string | null
  offset: number
}

export interface MorePlacesRequest {
  category: string | null
  tag: string | null
  lat: number
  lon: number
  mode: TransportMode
  offset: number
}

export interface MorePlacesResponse {
  places: Place[]
}

export interface ResolveLocationResponse {
  lat: number | null
  lon: number | null
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
