import { useEffect, useRef, useState, type CSSProperties } from 'react'
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
import { AgentsBadge, Pipeline } from './components/Pipeline'
import { HowItWorks } from './components/HowItWorks'
import { Personalize } from './components/Personalize'
import { StartHere } from './components/StartHere'
import { SPLIT_DEFAULT, SplitHandle } from './components/SplitHandle'
import { FactCheckLog, RecapView } from './components/RecapView'
import { LiveFeed, LiveStats, MatchGlance } from './components/Live'
import { ComparePane, type Side } from './components/Compare'
import { useLiveStream, type FeedItem, type LiveState } from './liveState'
import { sentenceEvents } from './matchEvents'
import { applyTheme, loadTheme, type Theme } from './theme'
import { loadLanguage, saveLanguage } from './language'
import { focusLabel } from './focus'
import { useMediaQuery } from './useMediaQuery'
import { readUrl, writeUrl, type Mode } from './urlState'
import { EMPTY_PIPELINE, applyProgress, type PipelineState } from './pipelineState'

const PASSCODE_KEY = 'itg-demo-passcode'
const OPENING_MATCH = 'match_005' // Ashvale Town 3-2 Harbourside City: a comeback, the best first impression

/** Computers with a mouse get the mini rail that opens on hover; touch screens get the ☰ drawer. Keep in sync with index.css. */
const RAIL_QUERY = '(hover: hover) and (pointer: fine) and (min-width: 901px)'

/** "Eastmoor United" -> "EU": a club's initials for the collapsed rail. */
const initials = (team: string) =>
  team
    .split(' ')
    .map((word) => word[0])
    .join('')
    .slice(0, 2)

// The view a shared link asks for (?match=5&mode=live&style=fan&lang=es&focus=Away). A link sets the
// whole view, so a missing language means English rather than this browser's last choice.
const LINKED = readUrl()
const FROM_LINK = window.location.search !== ''
if (LINKED.mode === 'live' && LINKED.focus && LINKED.focus !== 'Home' && LINKED.focus !== 'Away') {
  delete LINKED.focus // live commentary personalizes by club only
}

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

const SPLIT_KEY = 'itg-split'

/** The recap/evidence split the viewer chose last time (a per-browser convenience). */
function loadSplit(): number {
  try {
    const saved = Number(localStorage.getItem(SPLIT_KEY))
    return saved >= 35 && saved <= 70 ? saved : SPLIT_DEFAULT
  } catch {
    return SPLIT_DEFAULT
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
  const [style, setStyle] = useState<Style>(LINKED.style ?? 'broadcaster')
  const [language, setLanguage] = useState<Language>(() => LINKED.language ?? (FROM_LINK ? 'en' : loadLanguage()))
  const [focus, setFocus] = useState(LINKED.focus ?? '') // personalization: '', 'Home' / 'Away' (supported club) or a player id
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
  const [mode, setMode] = useState<Mode>(LINKED.mode ?? 'recap')
  const [showAllMatches, setShowAllMatches] = useState(false) // the rail lists only matches with recaps
  const liveA = useLiveStream() // the main view (and the left pane when comparing)
  const liveB = useLiveStream() // the right pane when comparing
  const live = liveA.state
  const [liveSelected, setLiveSelected] = useState<{ sentence: RecapSentence; item: FeedItem } | null>(null)
  const [speed, setSpeed] = useState(1)
  const [agentsOpen, setAgentsOpen] = useState(false) // the full agent pipeline under the "Verified by" badge
  const [howOpen, setHowOpen] = useState(false)
  const [navOpen, setNavOpen] = useState(false) // the ☰ drawer (touch screens)
  const rail = useMediaQuery(RAIL_QUERY) // mini rail that opens on hover (mouse screens)
  const wide = useMediaQuery('(min-width: 901px)') // side-by-side columns (the divider only makes sense then)
  const [split, setSplit] = useState(loadSplit) // recap side of the recap/evidence split, in percent
  const mainRef = useRef<HTMLElement>(null)
  const [railPicked, setRailPicked] = useState(false) // just picked a match: keep the rail shut until the mouse leaves
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
        // Open on the most exciting demo match (a 3-2 comeback) when it's there.
        setMatchId(
          (current) =>
            current ??
            list.find((m) => m.match_id === (LINKED.matchId ?? OPENING_MATCH))?.match_id ??
            list[0]?.match_id ??
            null,
        )
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
    const player = focus === 'Home' || focus === 'Away' ? '' : focus
    Promise.all([getMatch(matchId), getStats(matchId, player), getRecap(matchId, style, language, focus)])
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
  }, [matchId, style, language, focus])

  // When comparing, load the right pane's saved recap too.
  const otherKey = `${matchId}/${other.style}/${other.language}/${focus}`
  useEffect(() => {
    if (!compare || !matchId) return
    let cancelled = false
    getRecap(matchId, other.style, other.language, focus)
      .then(
        (r) => !cancelled && setOtherRecap({ key: `${matchId}/${other.style}/${other.language}/${focus}`, result: r }),
      )
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [compare, matchId, other.style, other.language, focus])

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
    // Live commentary personalizes by club only: following a player is a recap feature.
    if (next === 'live' && focus !== 'Home' && focus !== 'Away' && focus) chooseFocus('')
    setMode(next)
  }

  function chooseFocus(next: string) {
    if (next === focus) return
    resetView()
    setLoading(true)
    setFocus(next)
  }

  /** Play the match live: free with saved (or no) commentary; with `generate`, the agents commentate now. */
  async function startLive(generate: boolean, code = passcode) {
    if (!matchId) return
    resetLive()
    setAskPasscode(null)
    setError(null)
    const base = { matchId, generate, passcode: code, secondsPerMinute: speed, focus }
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

  // Keep the address bar in step with the view, so it can be copied and shared.
  useEffect(() => {
    if (matchId) writeUrl({ matchId, mode, style, language, focus })
  }, [matchId, mode, style, language, focus])

  // Remember the split for next time.
  useEffect(() => {
    try {
      if (split === SPLIT_DEFAULT) localStorage.removeItem(SPLIT_KEY)
      else localStorage.setItem(SPLIT_KEY, String(split))
    } catch {
      // storage blocked: the split just won't be remembered
    }
  }, [split])

  // Escape closes the match list.
  useEffect(() => {
    if (!navOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setNavOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [navOpen])

  function chooseMatch(id: string) {
    setNavOpen(false) // picking a match closes the list
    if (rail) {
      setRailPicked(true)
      ;(document.activeElement as HTMLElement | null)?.blur() // so keyboard focus doesn't hold the rail open
    }
    if (id === matchId) return
    resetView()
    setMatch(null) // so the old scoreboard doesn't linger while the new match loads
    setStats(null)
    setLoading(true)
    setFocus('') // clubs and players belong to the match
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
      const recap = await generateRecap(matchId, style, language, focus, code, (p) =>
        setPipeline((state) => applyProgress(state, p)),
      )
      setResult(recap)
      setSelected(recap.recap.headline)
      savePasscode(code)
      // Mark the new recap in the match list.
      setMatches((list) =>
        list.map((m) =>
          m.match_id === matchId && !focus && !hasRecap(m, style, language)
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
          getRecap(matchId, style, language, focus)
            .then((r) => setResult(r))
            .catch(() => {})
        }
      }
      setError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  /** Generate (or regenerate) the recap: asks for the demo passcode first if we don't have it. */
  function runAgents() {
    if (passcode) void generate()
    else setAskPasscode('recap')
  }

  const isLive = mode === 'live'
  // The rail shows the matches that have recaps (plus the open one); the rest are one click away.
  const withRecaps = matches.filter((m) => (m.recaps ?? []).length > 0 || m.match_id === matchId)
  const visibleMatches = showAllMatches || withRecaps.length === 0 ? matches : withRecaps
  const hiddenMatches = matches.length - visibleMatches.length
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
        <div className="brand">
          <button
            type="button"
            className="matches-button"
            aria-expanded={navOpen}
            aria-controls="match-list"
            onClick={() => setNavOpen(true)}
          >
            <span aria-hidden="true">☰</span> Matches
          </button>
          <div>
            <h1>Inside the Game</h1>
            <p className="tagline">AI football recaps where every sentence shows its proof.</p>
          </div>
        </div>
        <div className="topbar-right">
          <p className="synthetic-note">All teams, players and matches are synthetic.</p>
          <button type="button" className="how-button" onClick={() => setHowOpen(true)}>
            How it works
          </button>
          <ThemeToggle theme={theme} onChange={chooseTheme} />
        </div>
      </header>
      <HowItWorks open={howOpen} onClose={() => setHowOpen(false)} />

      <div className="layout">
        {navOpen && <div className="drawer-backdrop" onClick={() => setNavOpen(false)} aria-hidden="true" />}
        {/* A mini rail that opens on hover (mouse screens), or a drawer opened by ☰ (touch screens). */}
        <nav
          id="match-list"
          className={`match-list${navOpen ? ' open' : ''}${railPicked ? ' picked' : ''}`}
          aria-label="Matches"
          inert={!rail && !navOpen}
          onMouseLeave={() => setRailPicked(false)}
        >
          <div className="drawer-header">
            <h2>
              <span className="full">Matches</span>
              <span className="mini" aria-hidden="true">
                ☰
              </span>
            </h2>
            <button
              type="button"
              className="icon-button"
              aria-label="Close the match list"
              onClick={() => setNavOpen(false)}
            >
              ✕
            </button>
          </div>
          {listLoading && <MatchListSkeleton />}
          <ul hidden={listLoading}>
            {visibleMatches.map((m) => (
              <li key={m.match_id}>
                <button
                  type="button"
                  className={m.match_id === matchId ? 'active' : undefined}
                  onClick={() => chooseMatch(m.match_id)}
                  disabled={running}
                  aria-label={`${m.home_team} ${m.score.Home}, ${m.away_team} ${m.score.Away}`}
                >
                  <span className="mini" aria-hidden="true">
                    <span>
                      {initials(m.home_team)} <b>{m.score.Home}</b>
                    </span>
                    <span>
                      {initials(m.away_team)} <b>{m.score.Away}</b>
                    </span>
                  </span>
                  <span className="full">
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
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {!listLoading && hiddenMatches > 0 && (
            <button type="button" className="link-button show-all" onClick={() => setShowAllMatches(true)}>
              Show all {matches.length} matches
            </button>
          )}
        </nav>

        <main
          ref={mainRef}
          style={{ '--columns': `minmax(0, ${split}fr) minmax(0, ${100 - split}fr)` } as CSSProperties}
        >
          {wide && !compare && <SplitHandle split={split} onChange={setSplit} container={mainRef} />}
          {slowStart && (
            <p className="waking" role="status">
              Waking up the server… it sleeps when nobody is using it, so the first load takes about 15 seconds.
            </p>
          )}
          {/* The band: scoreboard, controls and agents on the left, the pitch on the right. Same columns as below. */}
          <section className="stage" aria-label="Match, controls and pitch">
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
                <Personalize
                  match={match}
                  style={style}
                  language={language}
                  focus={focus}
                  compare={compare}
                  live={isLive}
                  disabled={running || livePlaying}
                  onStyle={chooseStyle}
                  onLanguage={chooseLanguage}
                  onFocus={chooseFocus}
                  onCompare={toggleCompare}
                />
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
                        {/* Before kick-off the big button on the pitch starts it; after full time, this one replays. */}
                        {live.status === 'done' && (
                          <button
                            type="button"
                            className="primary"
                            onClick={() => void startLive(false)}
                            disabled={loading || !matchId}
                          >
                            ↻ Watch again
                          </button>
                        )}
                      </>
                    )}
                  </div>
                ) : (
                  !compare &&
                  result &&
                  !running && (
                    <button
                      type="button"
                      className="secondary run-agents"
                      onClick={runAgents}
                      title="Generate this recap again with the four agents (needs the demo passcode)"
                    >
                      ↻ Run the agents
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
                <AgentsBadge
                  running={running}
                  rewrites={running ? pipeline.rewrites : (result?.rewrites ?? 0)}
                  removed={running ? 0 : (result?.removed.length ?? 0)}
                  open={agentsOpen || running}
                  onToggle={() => setAgentsOpen(!agentsOpen)}
                />
              )}
              {!isLive && !compare && (running || (result && agentsOpen)) && (
                <Pipeline state={result && !running ? doneState(result.rewrites) : pipeline} />
              )}
              {!isLive && !compare && !running && !loading && !agentsOpen && <StartHere />}
              {!isLive && !compare && !running && !loading && !agentsOpen && match && stats && (
                <MatchGlance match={match} stats={stats} />
              )}
            </div>
            <div className="stage-pitch-cell">
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
                {isLive && live.status === 'idle' && !loading && match && (
                  <button type="button" className="pitch-cta" onClick={() => void startLive(false)}>
                    <span aria-hidden="true">▶</span> Watch this match live
                  </button>
                )}
                {!loading && note && !(isLive && live.status === 'idle') && <p className="stage-pitch-note">{note}</p>}
              </div>
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
              <div className="empty">
                <p>
                  No {style} recap ({LANGUAGES[language]}
                  {focus && `, for ${focusLabel(focus, match)}`}) for this match yet. Generating one runs the four
                  agents live (it takes a minute or two) and needs the demo passcode.
                </p>
                <button type="button" className="secondary" onClick={runAgents} disabled={loading || !matchId}>
                  Run the agents
                </button>
              </div>
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
