import type {
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
