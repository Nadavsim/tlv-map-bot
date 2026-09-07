import type { Place } from './types'

export type ChatEntry =
  | { id: string; kind: 'bot-text'; text: string }
  | { id: string; kind: 'user-text'; text: string }
  | { id: string; kind: 'places'; places: Place[] }

let nextId = 0

export function makeEntryId(): string {
  nextId += 1
  return `entry-${nextId}`
}
