import type { Focus, Match, MatchEvent } from './api'

/** A player the reader can follow, with a short hint of their match. */
export interface PlayerOption {
  id: string
  label: string
}

/** Everyone who touched the ball, home players first by shirt number, labelled with their goals. */
export function playerOptions(match: Match): PlayerOption[] {
  const goals = new Map<string, number>()
  const seen = new Map<string, MatchEvent['team']>()
  for (const e of match.events) {
    seen.set(e.player, e.team)
    if (e.type === 'shot' && e.outcome === 'goal') goals.set(e.player, (goals.get(e.player) ?? 0) + 1)
  }
  return [...seen.entries()]
    .sort(([a, ta], [b, tb]) => (ta === tb ? Number(a.slice(1)) - Number(b.slice(1)) : ta === 'Home' ? -1 : 1))
    .map(([id]) => {
      const n = goals.get(id) ?? 0
      return { id, label: n ? `${id} · ${n} goal${n === 1 ? '' : 's'}` : id }
    })
}

/** How a focus reads in sentences: "Eastmoor United fans", "player A11". */
export function focusLabel(focus: Focus, match: Match | null): string {
  if (focus === 'Home') return `${match?.home_team ?? 'home'} fans`
  if (focus === 'Away') return `${match?.away_team ?? 'away'} fans`
  return focus ? `player ${focus}` : ''
}
