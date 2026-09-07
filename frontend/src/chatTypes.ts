import type { Place } from './types'

export type ChatEntry =
  | { id: string; kind: 'bot-text'; text: string }
  | { id: string; kind: 'user-text'; text: string }
  | {
      id: string
      kind: 'places'
      places: Place[]
      // The category this batch was matched against (null = "surprise me" /
      // any category) - kept so "Show more" can fetch the next page of the
      // same query without re-running the LLM categorization.
      category: string | null
      offset: number
      hasMore: boolean
    }

let nextId = 0

export function makeEntryId(): string {
  nextId += 1
  return `entry-${nextId}`
}
