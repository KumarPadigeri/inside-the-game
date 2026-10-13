import type { Style } from '../api'

// Simple line icons (24x24, drawn with the current text colour).
const PATHS: Record<Style, string[]> = {
  // Megaphone: a cheering supporter.
  fan: ['M3 11v2a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1z', 'M15 9a3 3 0 0 1 0 6', 'M18 6.5a7 7 0 0 1 0 11'],
  // Bar chart: tactics and numbers.
  analyst: ['M3 20h18', 'M6 20v-6', 'M11 20V8', 'M16 20v-9', 'M21 20V4'],
  // Microphone: a TV presenter.
  broadcaster: ['M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z', 'M5 11a7 7 0 0 0 14 0', 'M12 18v3', 'M8 21h8'],
}

export function PersonaIcon({ style }: { style: Style }) {
  return (
    <svg
      className="persona-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[style].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  )
}
