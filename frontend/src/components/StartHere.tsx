import { useState } from 'react'

const KEY = 'itg-start-here-done'

function seen(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

/** First-visit guidance: three steps, dismissed once and remembered in this browser. */
export function StartHere() {
  const [hidden, setHidden] = useState(seen)
  if (hidden) return null

  function dismiss() {
    setHidden(true)
    try {
      localStorage.setItem(KEY, '1')
    } catch {
      // storage blocked: it just shows again next time
    }
  }

  return (
    <section className="start-here" aria-label="Start here">
      <ol>
        <li>
          <span className="step-number">1</span> Pick a match
        </li>
        <li>
          <span className="step-number">2</span> Click any sentence
        </li>
        <li>
          <span className="step-number">3</span> See its proof
        </li>
      </ol>
      <button type="button" className="link-button" onClick={dismiss}>
        Got it
      </button>
    </section>
  )
}
