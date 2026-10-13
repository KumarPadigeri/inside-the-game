// Light / dark mode. "system" follows the computer's setting; light or dark overrides it.
// The choice is kept in localStorage (a per-browser convenience; the page works without it).

export type Theme = 'system' | 'light' | 'dark'
export const THEMES: Theme[] = ['system', 'light', 'dark']

const KEY = 'itg-theme'

export function loadTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY)
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  } catch {
    return 'system'
  }
}

/** Apply the theme to the page (index.html does the same before the first paint) and remember it. */
export function applyTheme(theme: Theme) {
  const root = document.documentElement
  if (theme === 'system') delete root.dataset.theme
  else root.dataset.theme = theme
  try {
    if (theme === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, theme)
  } catch {
    // storage blocked: the theme still applies, it just won't be remembered
  }
}
