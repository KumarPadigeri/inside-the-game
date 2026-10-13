import type { Match, MatchEvent, RecapSentence } from './api'

/** The match events a sentence cites, in match order (unknown ids are skipped). */
export function sentenceEvents(match: Match, sentence: RecapSentence): MatchEvent[] {
  const byId = new Map(match.events.map((e) => [e.event_id, e]))
  return sentence.event_ids.map((id) => byId.get(id)).filter((e): e is MatchEvent => e !== undefined)
}

/** A short summary of what backs a sentence, e.g. "3 events · 1 stat". */
export function evidenceLabel(sentence: RecapSentence): string {
  const parts: string[] = []
  if (sentence.event_ids.length)
    parts.push(`${sentence.event_ids.length} event${sentence.event_ids.length === 1 ? '' : 's'}`)
  if (sentence.tools.includes('find_similar_moments')) parts.push('other matches')
  const stats = sentence.tools.filter((t) => t !== 'find_similar_moments').length
  if (stats) parts.push(`${stats} stat${stats === 1 ? '' : 's'}`)
  return parts.join(' · ')
}
