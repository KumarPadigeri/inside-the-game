// The recap language. Kept in localStorage (a per-browser convenience; the page works without it).

import { LANGUAGES, type Language } from './api'

const KEY = 'itg-language'

export function loadLanguage(): Language {
  try {
    const saved = localStorage.getItem(KEY)
    return saved && saved in LANGUAGES ? (saved as Language) : 'en'
  } catch {
    return 'en'
  }
}

export function saveLanguage(language: Language) {
  try {
    if (language === 'en') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, language)
  } catch {
    // storage blocked: the choice just won't be remembered
  }
}
