import type { Match, MatchEvent, RecapSentence } from './api'

/** The match events a sentence cites, in match order (unknown ids are skipped). */
export function sentenceEvents(match: Match, sentence: RecapSentence): MatchEvent[] {
  const byId = new Map(match.events.map((e) => [e.event_id, e]))
  return sentence.event_ids.map((id) => byId.get(id)).filter((e): e is MatchEvent => e !== undefined)
}
