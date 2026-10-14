// Shareable links: the address bar mirrors what's on screen, e.g. ?match=5&mode=live&style=fan&lang=es.
// Opening such a link restores that view. Defaults are left out to keep links short.

import { LANGUAGES, STYLES, type Language, type Style } from './api'

export type Mode = 'recap' | 'live'

export interface ViewState {
  matchId: string | null
  mode: Mode
  style: Style
  language: Language
  focus: string // '', 'Home' / 'Away' or a player id
}

const DEFAULTS = { mode: 'recap', style: 'broadcaster', language: 'en', focus: '' } as const

/** "5" or "match_005" -> "match_005". */
function matchIdFrom(value: string | null): string | null {
  if (!value) return null
  if (/^match_\d{3}$/.test(value)) return value
  return /^\d{1,3}$/.test(value) ? `match_${value.padStart(3, '0')}` : null
}

/** "match_005" -> "5" (the short form used in links). */
const shortMatchId = (id: string) => String(Number(id.replace('match_', '')))

/** The view the link asks for; anything missing or invalid is left out. */
export function readUrl(search = window.location.search): Partial<ViewState> {
  const params = new URLSearchParams(search)
  const view: Partial<ViewState> = {}
  const matchId = matchIdFrom(params.get('match'))
  if (matchId) view.matchId = matchId
  const mode = params.get('mode')
  if (mode === 'recap' || mode === 'live') view.mode = mode
  const style = params.get('style')
  if (style && (STYLES as string[]).includes(style)) view.style = style as Style
  const lang = params.get('lang')
  if (lang && lang in LANGUAGES) view.language = lang as Language
  const focus = params.get('focus')
  if (focus && /^(Home|Away|[HA]\d{1,2})$/.test(focus)) view.focus = focus
  return view
}

/** The query string for a view (without defaults), e.g. "?match=5&mode=live". */
export function toSearch(view: ViewState): string {
  const params = new URLSearchParams()
  if (view.matchId) params.set('match', shortMatchId(view.matchId))
  if (view.mode !== DEFAULTS.mode) params.set('mode', view.mode)
  if (view.style !== DEFAULTS.style) params.set('style', view.style)
  if (view.language !== DEFAULTS.language) params.set('lang', view.language)
  if (view.focus !== DEFAULTS.focus) params.set('focus', view.focus)
  const query = params.toString()
  return query ? `?${query}` : ''
}

/** Update the address bar without adding a history entry for every click. */
export function writeUrl(view: ViewState) {
  const search = toSearch(view)
  if (search !== window.location.search) {
    window.history.replaceState(null, '', `${window.location.pathname}${search}${window.location.hash}`)
  }
}
