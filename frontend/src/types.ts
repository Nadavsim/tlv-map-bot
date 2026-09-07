export type TransportMode = 'walking' | 'driving'

export interface ChatRequest {
  message: string
  lat: number
  lon: number
  mode: TransportMode
}

export interface Place {
  name: string
  category: string
  distance: string
  eta: string | null
  instagram_url: string | null
  maps_url: string
}

export interface ChatResponse {
  reply: string
  places: Place[]
  category: string | null
}

export interface MorePlacesRequest {
  category: string | null
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

// Matches backend.app.PAGE_SIZE - a page shorter than this means there's
// nothing left to fetch, so "Show more" hides itself.
export const PAGE_SIZE = 3

export interface Coordinates {
  lat: number
  lon: number
}
