import { useEffect, useState } from 'react'
import {
  STYLES,
  generateRecap,
  getMatch,
  getRecap,
  getStats,
  listMatches,
  type Match,
  type MatchSummary,
  type RecapSentence,
  type Stats,
  type Style,
  type VerifiedRecap,
} from './api'
import { Evidence } from './components/Evidence'
import { Pipeline } from './components/Pipeline'
import { FactCheckLog, RecapView } from './components/RecapView'
import { EMPTY_PIPELINE, applyProgress, type PipelineState } from './pipelineState'

export default function App() {
  const [matches, setMatches] = useState<MatchSummary[]>([])
  const [matchId, setMatchId] = useState<string | null>(null)
  const [style, setStyle] = useState<Style>('broadcaster')
  const [match, setMatch] = useState<Match | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [result, setResult] = useState<VerifiedRecap | null>(null)
  const [selected, setSelected] = useState<RecapSentence | null>(null)
  const [pipeline, setPipeline] = useState<PipelineState>(EMPTY_PIPELINE)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listMatches()
      .then((list) => {
        setMatches(list)
        setMatchId((current) => current ?? list[0]?.match_id ?? null)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  // Load the match, its stats and any saved recap whenever the match or style changes.
  useEffect(() => {
    if (!matchId) return
    let cancelled = false
    Promise.all([getMatch(matchId), getStats(matchId), getRecap(matchId, style)])
      .then(([m, s, r]) => {
        if (cancelled) return
        setMatch(m)
        setStats(s)
        setResult(r)
        setSelected(r?.recap.headline ?? null)
      })
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [matchId, style])

  /** Clear what belongs to the previous match or style before switching. */
  function resetView() {
    setResult(null)
    setSelected(null)
    setPipeline(EMPTY_PIPELINE)
  }

  function chooseMatch(id: string) {
    resetView()
    setMatchId(id)
  }

  function chooseStyle(next: Style) {
    resetView()
    setStyle(next)
  }

  async function generate() {
    if (!matchId) return
    setRunning(true)
    setError(null)
    resetView()
    try {
      const recap = await generateRecap(matchId, style, (p) => setPipeline((state) => applyProgress(state, p)))
      setResult(recap)
      setSelected(recap.recap.headline)
    } catch (e) {
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
        <p className="synthetic-note">All teams, players and matches are synthetic.</p>
      </header>

      <div className="layout">
        <nav className="match-list" aria-label="Matches">
          <h2>Matches</h2>
          <ul>
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
                >
                  {s}
                </button>
              ))}
            </div>
            <button type="button" className="primary" onClick={generate} disabled={running || !matchId}>
              {running ? 'Agents at work…' : result ? 'Regenerate recap' : 'Generate recap'}
            </button>
          </section>

          {(running || result) && <Pipeline state={result && !running ? doneState(result.rewrites) : pipeline} />}
          {error && <p className="error">{error}</p>}

          {result && match ? (
            <div className="recap-grid">
              <div>
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
                No {style} recap for this match yet. Generate one to watch the four agents work it out — it
                takes a minute or two.
              </p>
            )
          )}
        </main>
      </div>
    </div>
  )
}

/** A finished (or saved) recap: every step done, with the rewrites it took. */
function doneState(rewrites: number): PipelineState {
  return { steps: Object.fromEntries(Object.keys(EMPTY_PIPELINE.steps).map((k) => [k, 'done'])), rewrites }
}
