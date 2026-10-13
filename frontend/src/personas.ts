import type { Style } from './api'

/** Who each recap style is written as, shown as a tooltip next to its icon. */
export const PERSONAS: Record<Style, string> = {
  fan: 'A passionate supporter of the winning team',
  analyst: 'A calm tactical expert explaining why things happened',
  broadcaster: 'A TV presenter wrapping up the match, fair to both teams',
}
