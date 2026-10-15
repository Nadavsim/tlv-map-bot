import type {
  AuthConfigResponse,
  AuthResponse,
  CategoriesResponse,
  ChatRequest,
  ChatResponse,
  EtasRequest,
  EtasResponse,
  FavoriteIdsResponse,
  FavoritePlacesResponse,
  MorePlacesRequest,
  MorePlacesResponse,
  ResolveLocationResponse,
  SavedAddress,
  SavedAddressesResponse,
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

export function postEtas(body: EtasRequest): Promise<EtasResponse> {
  return postJSON<EtasResponse>('/api/etas', body)
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

// Account-scoped calls carry the in-memory access token as a bearer header -
// deliberately not the refresh cookie, so a cross-site request can't trigger
// them on its own.
async function authedJSON<TResponse>(
  method: 'GET' | 'POST' | 'DELETE',
  url: string,
  token: string,
  body?: unknown,
): Promise<TResponse> {
  const res = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    throw new ApiError(res.status, `Request to ${url} failed with status ${res.status}`)
  }
  return res.json() as Promise<TResponse>
}

export function getSavedAddresses(token: string): Promise<SavedAddressesResponse> {
  return authedJSON<SavedAddressesResponse>('GET', '/api/saved-addresses', token)
}

export async function postSavedAddress(
  token: string,
  body: { label: string; lat: number; lon: number },
): Promise<SavedAddress> {
  const data = await authedJSON<{ address: SavedAddress }>('POST', '/api/saved-addresses', token, body)
  return data.address
}

export async function deleteSavedAddress(token: string, id: string): Promise<void> {
  await authedJSON<{ ok: boolean }>('DELETE', `/api/saved-addresses/${encodeURIComponent(id)}`, token)
}

export async function deleteAccount(token: string): Promise<void> {
  await authedJSON<{ ok: boolean }>('DELETE', '/api/auth/me', token)
}

export function getFavoriteIds(token: string): Promise<FavoriteIdsResponse> {
  return authedJSON<FavoriteIdsResponse>('GET', '/api/favorites/ids', token)
}

// The favorites as ordinary result cards, nearest to the given spot first.
export function getFavoritePlaces(token: string, lat: number, lon: number): Promise<FavoritePlacesResponse> {
  return authedJSON<FavoritePlacesResponse>('GET', `/api/favorites?lat=${lat}&lon=${lon}`, token)
}

export async function postFavorite(token: string, placeId: string): Promise<void> {
  await authedJSON<{ id: string }>('POST', '/api/favorites', token, { place_id: placeId })
}

export async function deleteFavorite(token: string, placeId: string): Promise<void> {
  await authedJSON<{ ok: boolean }>('DELETE', `/api/favorites/${encodeURIComponent(placeId)}`, token)
}
