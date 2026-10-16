import { useRef, useState } from 'react'
import { THEMES, type Theme } from '../theme'
import { useDismiss } from '../useDismiss'

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

function ThemeIcon({ theme }: { theme: Theme }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[theme].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  )
}

/** One icon button in the header (showing the current choice) with a small System / Light / Dark menu. */
export function ThemeToggle({ theme, onChange }: { theme: Theme; onChange: (theme: Theme) => void }) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  useDismiss(open, root, () => setOpen(false))
  return (
    <div className="theme-menu" ref={root}>
      <button
        type="button"
        className="icon-button theme-button"
        aria-label={`Colour theme: ${LABELS[theme]}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <ThemeIcon theme={theme} />
      </button>
      {open && (
        <div className="theme-panel" role="menu" aria-label="Colour theme">
          {THEMES.map((t) => (
            <button
              type="button"
              key={t}
              role="menuitemradio"
              aria-checked={t === theme}
              className={t === theme ? 'active' : undefined}
              onClick={() => {
                onChange(t)
                setOpen(false)
              }}
            >
              <ThemeIcon theme={t} />
              {LABELS[t]}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
