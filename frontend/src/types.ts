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
}

export interface ResolveLocationResponse {
  lat: number | null
  lon: number | null
}

export interface Coordinates {
  lat: number
  lon: number
}
