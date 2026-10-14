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
import { LiveFeed, LiveStats } from './components/Live'
import { ComparePane, type Side } from './components/Compare'
import { useLiveStream, type FeedItem, type LiveState } from './liveState'
import { sentenceEvents } from './matchEvents'
import { PERSONAS } from './personas'
import { applyTheme, loadTheme, type Theme } from './theme'
import { loadLanguage, saveLanguage } from './language'
import { EMPTY_PIPELINE, applyProgress, type PipelineState } from './pipelineState'

const PASSCODE_KEY = 'itg-demo-passcode'

type Mode = 'recap' | 'live'

/** Live playback speeds: seconds per match minute (1× plays a match in about a minute and a half). */
const SPEEDS: [label: string, secondsPerMinute: number][] = [
  ['1×', 1],
  ['2×', 0.5],
  ['4×', 0.25],
]

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
  const [askPasscode, setAskPasscode] = useState<Mode | null>(null) // which action is waiting for the passcode
  const [theme, setTheme] = useState<Theme>(loadTheme)
  const [replay, setReplay] = useState(0) // bump to replay the ball on the pitch
  const [listLoading, setListLoading] = useState(true) // the match list hasn't arrived yet
  const [slowStart, setSlowStart] = useState(false) // ...and it's taking a while (the backend is waking up)
  const [loading, setLoading] = useState(true) // the selected match / recap is loading
  const [mode, setMode] = useState<Mode>('recap')
  const liveA = useLiveStream() // the main view (and the left pane when comparing)
  const liveB = useLiveStream() // the right pane when comparing
  const live = liveA.state
  const [liveSelected, setLiveSelected] = useState<{ sentence: RecapSentence; item: FeedItem } | null>(null)
  const [speed, setSpeed] = useState(1)
  const [compare, setCompare] = useState(false) // split view: two personas / languages side by side
  const [other, setOther] = useState<Side>({ style: 'fan', language: 'en' }) // the right pane
  // The right pane's saved recap, tagged with what it was loaded for (a stale tag means it's loading).
  const [otherRecap, setOtherRecap] = useState<{ key: string; result: VerifiedRecap | null } | null>(null)

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

  // When comparing, load the right pane's saved recap too.
  const otherKey = `${matchId}/${other.style}/${other.language}`
  useEffect(() => {
    if (!compare || !matchId) return
    let cancelled = false
    getRecap(matchId, other.style, other.language)
      .then((r) => !cancelled && setOtherRecap({ key: `${matchId}/${other.style}/${other.language}`, result: r }))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [compare, matchId, other.style, other.language])

  const livePlaying = live.status === 'playing' || liveB.state.status === 'playing'

  function stopLive() {
    liveA.stop()
    liveB.stop()
  }

  function resetLive() {
    liveA.reset()
    liveB.reset()
    setLiveSelected(null)
  }

  function toggleCompare() {
    resetLive()
    setAskPasscode(null)
    if (!compare && other.style === style && other.language === language) {
      // Start with a different persona on the right, so the two views differ.
      setOther({ style: STYLES.find((s) => s !== style) ?? 'fan', language })
    }
    setCompare(!compare)
  }

  function chooseOther(next: Side) {
    resetLive()
    setOther(next)
  }

  /** The left pane's picker changes the main persona and language. */
  function chooseSide(next: Side) {
    if (next.style !== style) chooseStyle(next.style)
    if (next.language !== language) chooseLanguage(next.language)
  }

  /** Clear what belongs to the previous match or style before switching. */
  function resetView() {
    setResult(null)
    setSelected(null)
    setPipeline(EMPTY_PIPELINE)
    resetLive()
  }

  function chooseMode(next: Mode) {
    if (next === mode) return
    resetLive()
    setAskPasscode(null)
    setMode(next)
  }

  /** Play the match live: free with saved (or no) commentary; with `generate`, the agents commentate now. */
  async function startLive(generate: boolean, code = passcode) {
    if (!matchId) return
    resetLive()
    setAskPasscode(null)
    setError(null)
    const base = { matchId, generate, passcode: code, secondsPerMinute: speed }
    try {
      // Comparing plays both panes on the same clock (replays only: the agents commentate one view at a time).
      await Promise.all([
        liveA.start({ ...base, style, language }),
        ...(compare && !generate ? [liveB.start({ ...base, ...other })] : []),
      ])
      if (generate) savePasscode(code)
    } catch (e) {
      if (e instanceof PasscodeError) {
        setPasscode('')
        savePasscode('')
        setAskPasscode('live')
      }
      setError((e as Error).message)
    }
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
    setAskPasscode(null)
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
        setAskPasscode('recap')
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

  const isLive = mode === 'live'
  const liveMatch: Match | null = match && { ...match, events: live.events }
  const pitchEvents = isLive
    ? liveSelected && liveMatch
      ? sentenceEvents(liveMatch, liveSelected.sentence)
      : (live.tick?.events ?? [])
    : match && selected
      ? sentenceEvents(match, selected)
      : []
  const note = isLive
    ? livePitchNote(live, liveSelected !== null)
    : pitchNote(running, result !== null || compare, selected, match)

  /** A split-view pane's recap: loading (undefined), not generated yet (null), or the verified recap. */
  const recapPane = (r: VerifiedRecap | null | undefined) =>
    r === undefined ? (
      <p className="muted">Loading…</p>
    ) : r === null ? (
      <p className="empty">No recap in this persona and language yet. Generate one in the single view.</p>
    ) : (
      <>
        <RecapView result={r} selected={selected} onSelect={setSelected} />
        <FactCheckLog result={r} collapsed />
      </>
    )

  /** A split-view pane's live feed. Both panes follow the same match clock. */
  const livePane = (state: LiveState) => (
    <>
      {state.status === 'idle' && <p className="muted">Press Watch live: both views play on the same clock.</p>}
      {state.status !== 'idle' && state.commentary === 'none' && (
        <p className="muted">Live stats only: no commentary is saved for this persona and language yet.</p>
      )}
      {match && (
        <LiveFeed
          feed={state.feed}
          mode={state.commentary}
          playing={state.status === 'playing'}
          events={live.events}
          teams={{ home: match.home_team, away: match.away_team }}
          selected={liveSelected?.sentence ?? null}
          onSelect={(sentence, item) => setLiveSelected({ sentence, item })}
        />
      )}
    </>
  )

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Inside the Game</h1>
          <p className="tagline">Match recaps where every sentence shows its proof.</p>
        </div>
        <div className="mode-tabs" role="tablist" aria-label="View">
          {(['recap', 'live'] as const).map((m) => (
            <button
              type="button"
              role="tab"
              key={m}
              aria-selected={mode === m}
              className={mode === m ? 'active' : undefined}
              onClick={() => chooseMode(m)}
              disabled={running}
            >
              {m === 'recap' ? 'Recap' : 'Live'}
              {m === 'live' && livePlaying && <span className="live-dot" aria-hidden="true" />}
            </button>
          ))}
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
                <section className="scoreboard" aria-label={isLive ? 'Live score' : 'Final score'}>
                  <span className="team home">{match.home_team}</span>
                  <span className="final">
                    {isLive ? (live.tick?.score.Home ?? 0) : match.score.Home} –{' '}
                    {isLive ? (live.tick?.score.Away ?? 0) : match.score.Away}
                    {isLive && (
                      <span className="clock">
                        {live.status === 'done' ? 'FT' : live.tick ? `${live.tick.minute}'` : 'Kick-off'}
                      </span>
                    )}
                  </span>
                  <span className="team away">{match.away_team}</span>
                </section>
              )}

              <section className="controls">
                <button
                  type="button"
                  className={`compare-toggle${compare ? ' active' : ''}`}
                  aria-pressed={compare}
                  onClick={toggleCompare}
                  disabled={running || livePlaying}
                  data-tooltip="Two personas or languages side by side"
                >
                  <CompareIcon />
                  Compare
                </button>
                {!compare && (
                  <>
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
                    <label className="language">
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
                  </>
                )}
                {askPasscode ? (
                  <form
                    className="passcode"
                    onSubmit={(e) => {
                      e.preventDefault()
                      void (askPasscode === 'live' ? startLive(true, passcode) : generate(passcode))
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
                ) : isLive ? (
                  <div className="live-actions">
                    {livePlaying ? (
                      <button type="button" className="primary" onClick={stopLive}>
                        ■ Stop
                      </button>
                    ) : (
                      <>
                        <label className="speed">
                          <select
                            aria-label="Playback speed"
                            value={speed}
                            onChange={(e) => setSpeed(Number(e.target.value))}
                          >
                            {SPEEDS.map(([label, value]) => (
                              <option key={value} value={value}>
                                {label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          type="button"
                          className="primary"
                          onClick={() => void startLive(false)}
                          disabled={loading || !matchId}
                        >
                          ▶ Watch live
                        </button>
                      </>
                    )}
                  </div>
                ) : (
                  !compare && (
                    <button
                      type="button"
                      className="primary"
                      onClick={() => (passcode ? void generate() : setAskPasscode('recap'))}
                      disabled={running || loading || !matchId}
                    >
                      {running ? 'Agents at work…' : result ? 'Regenerate recap' : 'Generate recap'}
                    </button>
                  )
                )}
              </section>

              {loading && !running && <span className="skeleton stage-skeleton" aria-hidden="true" />}
              {isLive && !loading && match && (
                <LiveStats tick={live.tick} teams={{ home: match.home_team, away: match.away_team }} />
              )}
              {!isLive && compare && !loading && (
                <p className="compare-hint">
                  Same match, same verified facts, two different experiences. Pick a persona and language for each side;
                  click any sentence to see where it happened.
                </p>
              )}
              {!isLive && !compare && (running || result) && (
                <Pipeline state={result && !running ? doneState(result.rewrites) : pipeline} />
              )}
            </div>
            <div className="stage-pitch">
              <Pitch
                events={pitchEvents}
                replay={isLive && !liveSelected ? (live.tick?.minute ?? 0) : replay}
                live={isLive && !liveSelected}
              />
              {(!isLive || liveSelected) && pitchEvents.length > 0 && (
                <button type="button" className="replay" onClick={() => setReplay((n) => n + 1)}>
                  ↻ Replay
                </button>
              )}
              {!loading && note && <p className="stage-pitch-note">{note}</p>}
            </div>
          </section>
          {error && <p className="error">{error}</p>}

          {compare && !loading && match && liveMatch ? (
            <div className="compare-grid">
              <ComparePane label="A" side={{ style, language }} onChange={chooseSide} disabled={running || livePlaying}>
                {isLive ? livePane(live) : recapPane(result)}
              </ComparePane>
              <ComparePane label="B" side={other} onChange={chooseOther} disabled={running || livePlaying}>
                {isLive
                  ? livePane(liveB.state)
                  : recapPane(otherRecap?.key === otherKey ? otherRecap.result : undefined)}
              </ComparePane>
            </div>
          ) : isLive && !loading && match && liveMatch ? (
            <div className="recap-grid">
              <div className="recap-column">
                <LiveNotice
                  live={live}
                  onCommentate={() => (passcode ? void startLive(true) : setAskPasscode('live'))}
                />
                <LiveFeed
                  feed={live.feed}
                  mode={live.commentary}
                  playing={live.status === 'playing'}
                  events={live.events}
                  teams={{ home: match.home_team, away: match.away_team }}
                  selected={liveSelected?.sentence ?? null}
                  onSelect={(sentence, item) => setLiveSelected({ sentence, item })}
                />
              </div>
              <aside aria-label="Evidence">
                {liveSelected ? (
                  <Evidence
                    sentence={liveSelected.sentence}
                    match={liveMatch}
                    stats={liveSelected.item.commentary?.stats ?? null}
                    comparisons={[]}
                    asOfMinute={liveSelected.item.moment.minute}
                  />
                ) : (
                  <p className="muted">Click a comment to see what proves it, as it stood at that minute.</p>
                )}
              </aside>
            </div>
          ) : loading && !running ? (
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

function CompareIcon() {
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
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M12 4v16" />
    </svg>
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

/** What the live view is doing, and the button to have the agents commentate. */
function LiveNotice({ live, onCommentate }: { live: LiveState; onCommentate: () => void }) {
  const playing = live.status === 'playing'
  const text =
    live.status === 'idle'
      ? 'Watch the match as it happens: events arrive minute by minute, the stats update from code, and every key moment gets a verified comment.'
      : live.commentary === 'live'
        ? 'The Commentator and Verifier agents are commentating live. Each comment is checked against the events so far.'
        : live.commentary === 'saved'
          ? 'Replaying commentary the agents wrote and the Verifier checked during an earlier live run.'
          : 'Live stats only: no commentary is saved for this style and language yet.'
  return (
    <div className="live-notice">
      <p>{text}</p>
      {!playing && live.status !== 'idle' && (
        <button type="button" className="secondary" onClick={onCommentate}>
          {live.commentary === 'none' ? 'Commentate with the agents' : 'Commentate again'}
        </button>
      )}
    </div>
  )
}

/** The pitch hint in live mode (null while it shows events). */
function livePitchNote(live: LiveState, hasSelection: boolean) {
  if (hasSelection) return null
  if (live.status === 'idle') return 'Press Watch live: the match plays minute by minute.'
  if (!live.tick?.events.length && live.status === 'playing') return 'No events this minute.'
  return null
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
