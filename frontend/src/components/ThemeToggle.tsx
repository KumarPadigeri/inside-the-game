import { THEMES, type Theme } from '../theme'

const LABELS: Record<Theme, string> = { system: 'System', light: 'Light', dark: 'Dark' }

// Simple line icons (24x24): a monitor, a sun and a moon.
const PATHS: Record<Theme, string[]> = {
  system: ['M3 5a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z', 'M8 20h8', 'M12 16v4'],
  light: [
    'M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8z',
    'M12 2v2',
    'M12 20v2',
    'M4.9 4.9l1.4 1.4',
    'M17.7 17.7l1.4 1.4',
    'M2 12h2',
    'M20 12h2',
    'M4.9 19.1l1.4-1.4',
    'M17.7 6.3l1.4-1.4',
  ],
  dark: ['M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z'],
}

/** System / Light / Dark switch for the header: icons only, named by tooltip and screen-reader label. */
export function ThemeToggle({ theme, onChange }: { theme: Theme; onChange: (theme: Theme) => void }) {
  return (
    <div className="theme-toggle" role="radiogroup" aria-label="Colour theme">
      {THEMES.map((t) => (
        <button
          type="button"
          key={t}
          role="radio"
          aria-checked={t === theme}
          aria-label={`${LABELS[t]} theme`}
          data-tooltip={LABELS[t]}
          className={t === theme ? 'active' : undefined}
          onClick={() => onChange(t)}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            {PATHS[t].map((d) => (
              <path key={d} d={d} />
            ))}
          </svg>
        </button>
      ))}
    </div>
  )
}
