// Typed client for the Inside the Game backend (inside_the_game/api.py).

export type Team = 'Home' | 'Away'
export type Style = 'fan' | 'analyst' | 'broadcaster'
export const STYLES: Style[] = ['fan', 'analyst', 'broadcaster']

export type Language = 'en' | 'es' | 'fr' | 'pt' | 'hi'
/** Each language by its own name, as speakers look for it in a picker. */
export const LANGUAGES: Record<Language, string> = {
  en: 'English',
  es: 'Español',
  fr: 'Français',
  pt: 'Português',
  hi: 'हिन्दी',
}

/** Personalization: '' (neutral), a supported club ('Home' / 'Away') or a followed player ('H9'). */
export type Focus = string

export interface SavedRecap {
  style: Style
  language: Language
}

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
  recaps?: SavedRecap[] // recaps already saved for this match
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
  recap: { style: Style; language: Language; focus?: Focus; headline: RecapSentence; sentences: RecapSentence[] }
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

interface PlayerMove {
  minute: number
  outcome: string
  event_ids: number[]
}

/** One player's match (player focus mode). */
export interface PlayerStats {
  player: string
  team: Team
  first_minute: number
  last_minute: number
  passes_attempted: number
  passes_completed: number
  pass_accuracy: number
  shots: number
  shots_on_target: number
  goals: { event_id: number; minute: number; score_after: string }[]
  tackles_won: number
  interceptions_won: number
  set_up_goals: PlayerMove[]
  counterattacks: PlayerMove[]
  event_ids: number[]
}

/** The same tool results the agents saw, keyed by tool name. */
export interface Stats {
  get_match_info: { home_team: string; away_team: string; final_score: Score }
  get_possession: Record<Team, PossessionStats>
  get_shots: Record<Team, ShotStats>
  get_goals: Goal[]
  get_counterattacks: Counterattack[]
  get_player_stats?: PlayerStats // only when following a player
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
export const getStats = (id: string, player = '') =>
  getJson<Stats>(`/api/matches/${id}/stats${player ? `?player=${player}` : ''}`)
const recapPath = (id: string, style: Style, language: Language, focus: Focus) =>
  `/api/matches/${id}/recaps/${style}?language=${language}&focus=${encodeURIComponent(focus)}`
export const getRecap = (id: string, style: Style, language: Language, focus: Focus = '') =>
  getJson<VerifiedRecap>(recapPath(id, style, language, focus))

/** Thrown when the server refuses to generate (missing or wrong demo passcode). */
export class PasscodeError extends Error {}

/** Read a Server-Sent Events stream from a fetch response, calling onEvent for each message. */
async function readEvents(response: Response, onEvent: (event: string, data: string) => void): Promise<void> {
  if (!response.body) throw new Error('The server sent no stream')
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
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
      if (event && data) onEvent(event, data) // skips pings and comments
    }
  }
}

async function refusal(response: Response): Promise<never> {
  if (response.status === 403) {
    const detail = ((await response.json()) as { detail?: string }).detail
    throw new PasscodeError(detail ?? 'Generating needs the demo passcode')
  }
  throw new Error(`Request failed: ${response.status}`)
}

/**
 * Run the agents for a match and follow along. The backend streams Server-Sent
 * Events; EventSource only supports GET, so we read the POST response stream.
 */
export async function generateRecap(
  id: string,
  style: Style,
  language: Language,
  focus: Focus,
  passcode: string,
  onProgress: (progress: Progress) => void,
): Promise<VerifiedRecap> {
  const response = await fetch(`${BASE}${recapPath(id, style, language, focus)}`, {
    method: 'POST',
    headers: passcode ? { 'X-Recap-Passcode': passcode } : {},
  })
  if (!response.ok) await refusal(response)
  let recap: VerifiedRecap | null = null
  await readEvents(response, (event, data) => {
    if (event === 'progress') onProgress(JSON.parse(data) as Progress)
    else if (event === 'recap') recap = JSON.parse(data) as VerifiedRecap
    else if (event === 'error') throw new Error((JSON.parse(data) as { detail: string }).detail)
  })
  if (!recap) throw new Error('The stream ended without a recap')
  return recap
}

// --- live mode -------------------------------------------------------------

/** Sent every match minute: that minute's events and the running stats. */
export interface LiveTick {
  minute: number
  score: Score
  possession: Record<Team, number>
  passes_completed: Record<Team, number>
  shots: Record<Team, number>
  on_target: Record<Team, number>
  events: MatchEvent[]
}

export interface LiveMoment {
  key: string
  kind: 'goal' | 'counterattack' | 'half-time' | 'full-time'
  minute: number
  team: Team | null
  event_ids: number[]
}

/** Verified sentences about a moment, with the stats as they stood at that minute. */
export interface Commentary {
  moment: LiveMoment
  sentences: RecapSentence[]
  stats: Stats
  rewrites: number
  removed: { text: string; problem: string }[]
}

export interface LiveStart {
  match_id: string
  style: Style
  language: Language
  commentary: 'saved' | 'none' | 'live' // replaying saved commentary, stats only, or agents commentating now
}

export type LiveMessage =
  | { type: 'start'; data: LiveStart }
  | { type: 'tick'; data: LiveTick }
  | { type: 'moment'; data: LiveMoment }
  | { type: 'commentary'; data: Commentary }
  | { type: 'done'; data: { minute: number; score: Score } }

/**
 * Play a match live. Watching (GET) is free: live stats, plus saved commentary if any.
 * With `generate`, the agents commentate now (POST, needs the passcode) and the run is saved.
 */
export async function streamLive(
  id: string,
  style: Style,
  language: Language,
  options: { generate: boolean; passcode: string; secondsPerMinute: number; focus: Focus; signal: AbortSignal },
  onMessage: (message: LiveMessage) => void,
): Promise<void> {
  const query = `?language=${language}&focus=${options.focus}&seconds_per_minute=${options.secondsPerMinute}`
  const response = await fetch(`${BASE}/api/matches/${id}/live/${style}${query}`, {
    method: options.generate ? 'POST' : 'GET',
    headers: options.generate && options.passcode ? { 'X-Recap-Passcode': options.passcode } : {},
    signal: options.signal,
  })
  if (!response.ok) await refusal(response)
  await readEvents(response, (event, data) => {
    if (event === 'error') throw new Error((JSON.parse(data) as { detail: string }).detail)
    onMessage({ type: event, data: JSON.parse(data) } as LiveMessage)
  })
}
