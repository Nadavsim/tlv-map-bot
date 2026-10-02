import type { Coordinates, Place } from './types'

export type ChatEntry =
  | { id: string; kind: 'bot-text'; text: string }
  | { id: string; kind: 'user-text'; text: string }
  | {
      id: string
      kind: 'places'
      places: Place[]
      // Where the search was run from - the map's "you are here" pin. Kept on
      // the entry (not read from live app state) so an old result's map still
      // shows the location it was actually searched from after the user
      // switches Live/Custom or changes address.
      origin: Coordinates
      // The category/dietary tag this batch was matched against (category
      // null = "surprise me" / any category) - kept so "Show more" (and a
      // natural-language followup like "something else") can fetch the
      // next page of the same query without re-running the LLM
      // categorization.
      category: string | null
      dietaryTag: string | null
      offset: number
      hasMore: boolean
    }

let nextId = 0

export function makeEntryId(): string {
  nextId += 1
  return `entry-${nextId}`
}
