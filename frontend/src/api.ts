// Typed client for the Inside the Game backend (inside_the_game/api.py).

export type Team = 'Home' | 'Away'
export type Style = 'fan' | 'analyst' | 'broadcaster'
export const STYLES: Style[] = ['fan', 'analyst', 'broadcaster']

export interface MatchEvent {
  event_id: number
  minute: number
  team: Team
  player: string
  type: string
  x: number // 0-100, from the acting team's own goal toward the goal it attacks
  y: number
  outcome: string
  possession_id: number
}

export interface Score {
  Home: number
  Away: number
}

export interface MatchSummary {
  match_id: string
  home_team: string
  away_team: string
  score: Score
}

export interface Match extends MatchSummary {
  seed: number
  events: MatchEvent[]
}

export interface Moment {
  moment_id: string
  match_id: string
  home_team: string
  away_team: string
  team: Team
  kind: string
  minute: number
  score_before: string
  score_after: string
  description: string
  event_ids: number[]
}

export interface SimilarMoment extends Moment {
  similarity: number
}

export interface Comparison {
  claim: string
  moment: Moment
  similar: SimilarMoment[]
  event_ids: number[]
}

export interface RecapSentence {
  text: string
  finding_ids: number[]
  event_ids: number[]
  tools: string[]
}

export interface VerifiedRecap {
  recap: { style: Style; headline: RecapSentence; sentences: RecapSentence[] }
  comparisons: Comparison[]
  rewrites: number
  rejections: { draft: number; text: string; problem: string }[]
  removed: { text: string; problem: string }[]
}

export interface ShotStats {
  total: number
  on_target: number
  goals: number
  saved: number
  missed: number
  blocked: number
  event_ids: number[]
}

export interface PossessionStats {
  percent: number
  passes_attempted: number
  passes_completed: number
  pass_accuracy: number
}

export interface Goal {
  event_id: number
  minute: number
  team: Team
  player: string
  score_after: string
  buildup_event_ids: number[]
}

export interface Counterattack {
  possession_id: number
  team: Team
  minute: number
  won_by: string
  won_at_x: number
  passes: number
  outcome: string
  event_ids: number[]
}

/** The same tool results the agents saw, keyed by tool name. */
export interface Stats {
  get_match_info: { home_team: string; away_team: string; final_score: Score }
  get_possession: Record<Team, PossessionStats>
  get_shots: Record<Team, ShotStats>
  get_goals: Goal[]
  get_counterattacks: Counterattack[]
}

export interface Progress {
  step: string // start, analyst, retrieval, narrator, verifier
  status: 'started' | 'finished'
  detail: string // e.g. "rewrite 1"
}

// In development Vite proxies /api to the local backend; in production set VITE_API_URL.
const BASE = import.meta.env.VITE_API_URL ?? ''

async function getJson<T>(path: string): Promise<T | null> {
  const response = await fetch(`${BASE}${path}`)
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${path}: ${response.status} ${response.statusText}`)
  return (await response.json()) as T
}

export const listMatches = () => getJson<MatchSummary[]>('/api/matches').then((m) => m ?? [])
export const getMatch = (id: string) => getJson<Match>(`/api/matches/${id}`)
export const getStats = (id: string) => getJson<Stats>(`/api/matches/${id}/stats`)
export const getRecap = (id: string, style: Style) => getJson<VerifiedRecap>(`/api/matches/${id}/recaps/${style}`)

/** Thrown when the server refuses to generate (missing or wrong demo passcode). */
export class PasscodeError extends Error {}

/**
 * Run the agents for a match and follow along. The backend streams Server-Sent
 * Events; EventSource only supports GET, so we read the POST response stream.
 */
export async function generateRecap(
  id: string,
  style: Style,
  passcode: string,
  onProgress: (progress: Progress) => void,
): Promise<VerifiedRecap> {
  const response = await fetch(`${BASE}/api/matches/${id}/recaps/${style}`, {
    method: 'POST',
    headers: passcode ? { 'X-Recap-Passcode': passcode } : {},
  })
  if (response.status === 403) {
    const detail = ((await response.json()) as { detail?: string }).detail
    throw new PasscodeError(detail ?? 'Generating recaps needs the demo passcode')
  }
  if (!response.ok || !response.body) throw new Error(`Recap failed: ${response.status}`)

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  let recap: VerifiedRecap | null = null
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value.replace(/\r\n/g, '\n')
    let end: number
    while ((end = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      const event = /^event: (.*)$/m.exec(block)?.[1]
      const data = block
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice(6))
        .join('\n')
      if (!event || !data) continue // pings and comments
      if (event === 'progress') onProgress(JSON.parse(data) as Progress)
      else if (event === 'recap') recap = JSON.parse(data) as VerifiedRecap
      else if (event === 'error') throw new Error((JSON.parse(data) as { detail: string }).detail)
    }
  }
  if (!recap) throw new Error('The stream ended without a recap')
  return recap
}
