import type { ChatRequest, ChatResponse, ResolveLocationResponse } from './types'

async function postJSON<TResponse>(url: string, body: unknown): Promise<TResponse> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`Request to ${url} failed with status ${res.status}`)
  }
  return res.json() as Promise<TResponse>
}

export function postChat(body: ChatRequest): Promise<ChatResponse> {
  return postJSON<ChatResponse>('/api/chat', body)
}

export function resolveLocation(text: string): Promise<ResolveLocationResponse> {
  return postJSON<ResolveLocationResponse>('/api/resolve-location', { text })
}
