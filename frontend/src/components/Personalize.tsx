import { useRef, useState } from 'react'
import { LANGUAGES, STYLES, type Language, type Match, type Style } from '../api'
import { playerOptions } from '../focus'
import { PERSONAS } from '../personas'
import { PersonaIcon } from './PersonaIcon'
import { useDismiss } from '../useDismiss'

interface PersonalizeProps {
  match: Match | null
  style: Style
  language: Language
  focus: string
  compare: boolean
  live: boolean // live commentary personalizes by club only
  disabled: boolean
  onStyle: (style: Style) => void
  onLanguage: (language: Language) => void
  onFocus: (focus: string) => void
  onCompare: () => void
}

const capitalized = (s: string) => s[0].toUpperCase() + s.slice(1)

/** The short summary on the button, e.g. "Fan · Español · Eastmoor United". */
function summary({ match, style, language, focus, compare }: PersonalizeProps): string {
  if (compare) return 'Comparing two versions'
  const parts = [capitalized(style), LANGUAGES[language]]
  if (focus === 'Home' && match) parts.push(match.home_team)
  else if (focus === 'Away' && match) parts.push(match.away_team)
  else if (focus) parts.push(`following ${focus}`)
  return parts.join(' · ')
}

/**
 * One button for every way to personalize the recap: who tells it, the language, a club or player,
 * and the side-by-side comparison. The choices open in a small panel instead of crowding the page.
 * They apply at once; a click outside, Esc or the button itself closes the panel.
 */
export function Personalize(props: PersonalizeProps) {
  const { match, style, language, focus, compare, live, disabled, onStyle, onLanguage, onFocus, onCompare } = props
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  // Close on a click outside the panel, or on Escape.
  useDismiss(open, root, () => setOpen(false))

  return (
    <div className="personalize" ref={root}>
      <button
        type="button"
        className="personalize-button"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen(!open)}
        disabled={disabled}
      >
        {compare ? <span aria-hidden="true">⇆</span> : <PersonaIcon style={style} />}
        <span className="personalize-summary">{summary(props)}</span>
        <span className="chevron" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && (
        <div className="personalize-panel" role="dialog" aria-label="Personalize the recap">
          <fieldset disabled={compare}>
            <legend>Who tells it</legend>
            {STYLES.map((s) => (
              <label key={s} className={`persona-option${s === style ? ' active' : ''}`}>
                <input type="radio" name="persona" checked={s === style} onChange={() => onStyle(s)} />
                <PersonaIcon style={s} />
                <span>
                  <strong>{capitalized(s)}</strong>
                  <span className="muted">{PERSONAS[s]}</span>
                </span>
              </label>
            ))}
          </fieldset>

          <div className="personalize-row">
            <label>
              <span className="field-label">Language</span>
              <select value={language} onChange={(e) => onLanguage(e.target.value as Language)} disabled={compare}>
                {Object.entries(LANGUAGES).map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            {match && (
              <label>
                <span className="field-label">For you</span>
                <select value={focus} onChange={(e) => onFocus(e.target.value)}>
                  <option value="">Neutral</option>
                  <optgroup label="Support a club">
                    <option value="Home">{match.home_team}</option>
                    <option value="Away">{match.away_team}</option>
                  </optgroup>
                  {!live && (
                    <optgroup label="Follow a player">
                      {playerOptions(match).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </label>
            )}
          </div>

          <label className="compare-switch">
            <input type="checkbox" role="switch" checked={compare} onChange={onCompare} />
            <span>
              <strong>Compare side by side</strong>
              <span className="muted">Two personas or languages for the same match, each with its own picker.</span>
            </span>
          </label>
        </div>
      )}
    </div>
  )
}
