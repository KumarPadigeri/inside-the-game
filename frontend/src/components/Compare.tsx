import type { ReactNode } from 'react'
import { LANGUAGES, STYLES, type Language, type Style } from '../api'
import { PERSONAS } from '../personas'
import { PersonaIcon } from './PersonaIcon'

export interface Side {
  style: Style
  language: Language
}

interface ComparePaneProps {
  label: string // "A" or "B", for screen readers
  side: Side
  onChange: (side: Side) => void
  disabled: boolean
  children: ReactNode
}

/** One half of the split view: its own persona and language, and its own recap or live feed. */
export function ComparePane({ label, side, onChange, disabled, children }: ComparePaneProps) {
  return (
    <section className="compare-pane" aria-label={`View ${label}: ${side.style}, ${LANGUAGES[side.language]}`}>
      <header className="compare-pane-header">
        <div className="styles compact" role="radiogroup" aria-label={`View ${label} persona`}>
          {STYLES.map((s) => (
            <button
              type="button"
              key={s}
              role="radio"
              aria-checked={s === side.style}
              className={s === side.style ? 'active' : undefined}
              onClick={() => onChange({ ...side, style: s })}
              disabled={disabled}
              data-tooltip={PERSONAS[s]}
              aria-label={s}
            >
              <PersonaIcon style={s} />
              {s === side.style && s}
            </button>
          ))}
        </div>
        <label className="language">
          <select
            aria-label={`View ${label} language`}
            value={side.language}
            onChange={(e) => onChange({ ...side, language: e.target.value as Language })}
            disabled={disabled}
          >
            {Object.entries(LANGUAGES).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </header>
      <div className="compare-pane-body">{children}</div>
    </section>
  )
}
