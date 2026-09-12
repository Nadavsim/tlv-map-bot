import type {
  AuthConfigResponse,
  AuthResponse,
  CategoriesResponse,
  ChatRequest,
  ChatResponse,
  MorePlacesRequest,
  MorePlacesResponse,
  ResolveLocationResponse,
} from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function postJSON<TResponse>(url: string, body: unknown): Promise<TResponse> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new ApiError(res.status, `Request to ${url} failed with status ${res.status}`)
  }
  return res.json() as Promise<TResponse>
}

export function postChat(body: ChatRequest): Promise<ChatResponse> {
  return postJSON<ChatResponse>('/api/chat', body)
}

export function postMorePlaces(body: MorePlacesRequest): Promise<MorePlacesResponse> {
  return postJSON<MorePlacesResponse>('/api/more-places', body)
}

export async function getCategories(): Promise<CategoriesResponse> {
  const res = await fetch('/api/categories')
  if (!res.ok) {
    throw new ApiError(res.status, `Request to /api/categories failed with status ${res.status}`)
  }
  return res.json() as Promise<CategoriesResponse>
}

export function resolveLocation(text: string): Promise<ResolveLocationResponse> {
  return postJSON<ResolveLocationResponse>('/api/resolve-location', { text })
}

export async function getAuthConfig(): Promise<AuthConfigResponse> {
  const res = await fetch('/api/auth/config')
  if (!res.ok) {
    throw new ApiError(res.status, `Request to /api/auth/config failed with status ${res.status}`)
  }
  return res.json() as Promise<AuthConfigResponse>
}

export function postGoogleAuth(credential: string): Promise<AuthResponse> {
  return postJSON<AuthResponse>('/api/auth/google', { credential })
}

// No body needed - the refresh token travels as an httpOnly cookie, sent
// automatically on this same-origin request without any credentials option.
// Returns null (not a rejected promise) on a 401 - "not signed in" is an
// entirely expected outcome here (e.g. every fresh visitor), not an error.
export async function postRefresh(): Promise<AuthResponse | null> {
  const res = await fetch('/api/auth/refresh', { method: 'POST' })
  if (res.status === 401) return null
  if (!res.ok) {
    throw new ApiError(res.status, `Request to /api/auth/refresh failed with status ${res.status}`)
  }
  return res.json() as Promise<AuthResponse>
}

export async function postLogout(): Promise<void> {
  await fetch('/api/auth/logout', { method: 'POST' })
}
