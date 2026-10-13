import { useEffect, useState } from 'react'
import {
  LANGUAGES,
  PasscodeError,
  STYLES,
  generateRecap,
  getMatch,
  getRecap,
  getStats,
  listMatches,
  type Language,
  type Match,
  type MatchSummary,
  type RecapSentence,
  type Stats,
  type Style,
  type VerifiedRecap,
} from './api'
import { Evidence } from './components/Evidence'
import { Pitch } from './components/Pitch'
import { MatchListSkeleton, RecapSkeleton, ScoreboardSkeleton } from './components/Skeleton'
import { ThemeToggle } from './components/ThemeToggle'
import { PersonaIcon } from './components/PersonaIcon'
import { Pipeline } from './components/Pipeline'
import { FactCheckLog, RecapView } from './components/RecapView'
import { sentenceEvents } from './matchEvents'
import { PERSONAS } from './personas'
import { applyTheme, loadTheme, type Theme } from './theme'
import { loadLanguage, saveLanguage } from './language'
import { EMPTY_PIPELINE, applyProgress, type PipelineState } from './pipelineState'

const PASSCODE_KEY = 'itg-demo-passcode'

// The passcode lives only in this tab (sessionStorage), which can be unavailable: never rely on it.
function loadPasscode(): string {
  try {
    return sessionStorage.getItem(PASSCODE_KEY) ?? ''
  } catch {
    return ''
  }
}

function savePasscode(value: string) {
  try {
    if (value) sessionStorage.setItem(PASSCODE_KEY, value)
    else sessionStorage.removeItem(PASSCODE_KEY)
  } catch {
    // storage blocked: the passcode just won't be remembered
  }
}

export default function App() {
  const [matches, setMatches] = useState<MatchSummary[]>([])
  const [matchId, setMatchId] = useState<string | null>(null)
  const [style, setStyle] = useState<Style>('broadcaster')
  const [language, setLanguage] = useState<Language>(loadLanguage)
  const [match, setMatch] = useState<Match | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [result, setResult] = useState<VerifiedRecap | null>(null)
  const [selected, setSelected] = useState<RecapSentence | null>(null)
  const [pipeline, setPipeline] = useState<PipelineState>(EMPTY_PIPELINE)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [passcode, setPasscode] = useState(loadPasscode)
  const [askPasscode, setAskPasscode] = useState(false)
  const [theme, setTheme] = useState<Theme>(loadTheme)
  const [replay, setReplay] = useState(0) // bump to replay the ball on the pitch
  const [listLoading, setListLoading] = useState(true) // the match list hasn't arrived yet
  const [slowStart, setSlowStart] = useState(false) // ...and it's taking a while (the backend is waking up)
  const [loading, setLoading] = useState(true) // the selected match / recap is loading

  function chooseTheme(next: Theme) {
    applyTheme(next)
    setTheme(next)
  }

  useEffect(() => {
    // The backend scales to zero when idle; if the first answer is slow, say why instead of looking broken.
    const timer = setTimeout(() => setSlowStart(true), 2500)
    listMatches()
      .then((list) => {
        setMatches(list)
        setMatchId((current) => current ?? list[0]?.match_id ?? null)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => {
        clearTimeout(timer)
        setListLoading(false)
        setSlowStart(false)
      })
    return () => clearTimeout(timer)
  }, [])

  // Load the match, its stats and any saved recap whenever the match, style or language changes.
  useEffect(() => {
    if (!matchId) return
    let cancelled = false
    Promise.all([getMatch(matchId), getStats(matchId), getRecap(matchId, style, language)])
      .then(([m, s, r]) => {
        if (cancelled) return
        setMatch(m)
        setStats(s)
        setResult(r)
        setSelected(r?.recap.headline ?? null)
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [matchId, style, language])

  /** Clear what belongs to the previous match or style before switching. */
  function resetView() {
    setResult(null)
    setSelected(null)
    setPipeline(EMPTY_PIPELINE)
  }

  function chooseMatch(id: string) {
    if (id === matchId) return
    resetView()
    setMatch(null) // so the old scoreboard doesn't linger while the new match loads
    setStats(null)
    setLoading(true)
    setMatchId(id)
  }

  function chooseStyle(next: Style) {
    if (next === style) return
    resetView()
    setLoading(true)
    setStyle(next)
  }

  function chooseLanguage(next: Language) {
    if (next === language) return
    resetView()
    setLoading(true)
    setLanguage(next)
    saveLanguage(next)
  }

  async function generate(code = passcode) {
    if (!matchId) return
    setAskPasscode(false)
    setRunning(true)
    setError(null)
    resetView()
    try {
      const recap = await generateRecap(matchId, style, language, code, (p) =>
        setPipeline((state) => applyProgress(state, p)),
      )
      setResult(recap)
      setSelected(recap.recap.headline)
      savePasscode(code)
      // Mark the new recap in the match list.
      setMatches((list) =>
        list.map((m) =>
          m.match_id === matchId && !hasRecap(m, style, language)
            ? { ...m, recaps: [...(m.recaps ?? []), { style, language }] }
            : m,
        ),
      )
    } catch (e) {
      if (e instanceof PasscodeError) {
        setPasscode('')
        savePasscode('')
        setAskPasscode(true)
        // Bring back the saved recap (if any) that was cleared when we started.
        if (matchId) {
          getRecap(matchId, style, language)
            .then((r) => setResult(r))
            .catch(() => {})
        }
      }
      setError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Inside the Game</h1>
          <p className="tagline">Match recaps where every sentence shows its proof.</p>
        </div>
        <div className="topbar-right">
          <p className="synthetic-note">All teams, players and matches are synthetic.</p>
          <ThemeToggle theme={theme} onChange={chooseTheme} />
        </div>
      </header>

      <div className="layout">
        <nav className="match-list" aria-label="Matches">
          <h2>Matches</h2>
          {slowStart && (
            <p className="waking" role="status">
              Waking up the server… it sleeps when nobody is using it, so the first load takes about 15 seconds.
            </p>
          )}
          {listLoading && <MatchListSkeleton />}
          <ul hidden={listLoading}>
            {matches.map((m) => (
              <li key={m.match_id}>
                <button
                  type="button"
                  className={m.match_id === matchId ? 'active' : undefined}
                  onClick={() => chooseMatch(m.match_id)}
                  disabled={running}
                >
                  <span className="teams">
                    {m.home_team}
                    <br />
                    {m.away_team}
                    <RecapMarks styles={STYLES.filter((s) => hasRecap(m, s, language))} language={language} />
                  </span>
                  <span className="score">
                    {m.score.Home}
                    <br />
                    {m.score.Away}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <main>
          {/* The band: scoreboard, styles and agents on the left, the pitch on the right. Same columns as below. */}
          <section className="stage" aria-label="Match, agents and pitch">
            <div className="stage-left">
              {!match && <ScoreboardSkeleton />}
              {match && (
                <section className="scoreboard" aria-label="Final score">
                  <span className="team home">{match.home_team}</span>
                  <span className="final">
                    {match.score.Home} – {match.score.Away}
                  </span>
                  <span className="team away">{match.away_team}</span>
                </section>
              )}

              <section className="controls">
                <div className="styles" role="radiogroup" aria-label="Recap style">
                  {STYLES.map((s) => (
                    <button
                      type="button"
                      key={s}
                      role="radio"
                      aria-checked={s === style}
                      className={s === style ? 'active' : undefined}
                      onClick={() => chooseStyle(s)}
                      disabled={running}
                      data-tooltip={PERSONAS[s]}
                      aria-description={PERSONAS[s]}
                    >
                      <PersonaIcon style={s} />
                      {s}
                    </button>
                  ))}
                </div>
                <label className="language" data-tooltip="Recap language">
                  <GlobeIcon />
                  <select
                    aria-label="Recap language"
                    value={language}
                    onChange={(e) => chooseLanguage(e.target.value as Language)}
                    disabled={running}
                  >
                    {Object.entries(LANGUAGES).map(([code, name]) => (
                      <option key={code} value={code}>
                        {name}
                      </option>
                    ))}
                  </select>
                </label>
                {askPasscode ? (
                  <form
                    className="passcode"
                    onSubmit={(e) => {
                      e.preventDefault()
                      void generate(passcode)
                    }}
                  >
                    <label htmlFor="passcode">Demo passcode</label>
                    <input
                      id="passcode"
                      type="password"
                      autoComplete="off"
                      value={passcode}
                      onChange={(e) => setPasscode(e.target.value)}
                      autoFocus
                    />
                    <button type="submit" className="primary" disabled={!passcode}>
                      Run agents
                    </button>
                  </form>
                ) : (
                  <button
                    type="button"
                    className="primary"
                    onClick={() => (passcode ? void generate() : setAskPasscode(true))}
                    disabled={running || loading || !matchId}
                  >
                    {running ? 'Agents at work…' : result ? 'Regenerate recap' : 'Generate recap'}
                  </button>
                )}
              </section>

              {loading && !running && <span className="skeleton stage-skeleton" aria-hidden="true" />}
              {(running || result) && <Pipeline state={result && !running ? doneState(result.rewrites) : pipeline} />}
            </div>
            <div className="stage-pitch">
              <Pitch events={match && selected ? sentenceEvents(match, selected) : []} replay={replay} />
              {match && selected && sentenceEvents(match, selected).length > 0 && (
                <button type="button" className="replay" onClick={() => setReplay((n) => n + 1)}>
                  ↻ Replay
                </button>
              )}
              {!loading && pitchNote(running, result !== null, selected, match) && (
                <p className="stage-pitch-note">{pitchNote(running, result !== null, selected, match)}</p>
              )}
            </div>
          </section>
          {error && <p className="error">{error}</p>}

          {loading && !running ? (
            <>
              <p className="visually-hidden" role="status">
                Loading
              </p>
              <RecapSkeleton />
            </>
          ) : result && match ? (
            <div className="recap-grid">
              <div className="recap-column">
                <RecapView result={result} selected={selected} onSelect={setSelected} />
                <FactCheckLog result={result} />
              </div>
              <aside aria-label="Evidence">
                {selected ? (
                  <Evidence sentence={selected} match={match} stats={stats} comparisons={result.comparisons} />
                ) : (
                  <p className="muted">Click a sentence to see what proves it.</p>
                )}
              </aside>
            </div>
          ) : (
            !running && (
              <p className="empty">
                No {style} recap ({LANGUAGES[language]}) for this match yet. Generating one runs the four agents live
                (it takes a minute or two) and needs the demo passcode.
              </p>
            )
          )}
        </main>
      </div>
    </div>
  )
}

function hasRecap(match: MatchSummary, style: Style, language: Language): boolean {
  return (match.recaps ?? []).some((r) => r.style === style && r.language === language)
}

/** Small persona icons on a match card: lit for each style that has a recap in the chosen language. */
function RecapMarks({ styles, language }: { styles: Style[]; language: Language }) {
  return (
    // Described with a label, not hidden text: a positioned hidden element escapes the scrolling match strip.
    <span
      className="recap-marks"
      role="img"
      aria-label={styles.length ? `${LANGUAGES[language]} recaps: ${styles.join(', ')}` : 'No recaps yet'}
    >
      {STYLES.map((s) => (
        <span key={s} className={styles.includes(s) ? 'has' : undefined}>
          <PersonaIcon style={s} />
        </span>
      ))}
    </span>
  )
}

function GlobeIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z" />
    </svg>
  )
}

/** The hint shown on the pitch when it has no events to draw (null when it has some). */
function pitchNote(running: boolean, hasRecap: boolean, selected: RecapSentence | null, match: Match | null) {
  if (running) return 'The agents are working…'
  if (!hasRecap) return 'Generate a recap, then click a sentence to see where it happened.'
  if (!selected || !match) return 'Click a sentence to see where it happened.'
  if (sentenceEvents(match, selected).length === 0) return 'This sentence is backed by stats, not specific moments.'
  return null
}

/** A finished (or saved) recap: every step done, with the rewrites it took. */
function doneState(rewrites: number): PipelineState {
  return { steps: Object.fromEntries(Object.keys(EMPTY_PIPELINE.steps).map((k) => [k, 'done'])), rewrites }
}
