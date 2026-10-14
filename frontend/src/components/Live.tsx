import type { ReactNode } from 'react'
import type { LiveMoment, LiveStart, LiveTick, Match, MatchEvent, RecapSentence, Stats, Team } from '../api'
import type { FeedItem } from '../liveState'
import { evidenceLabel } from '../matchEvents'

interface Teams {
  home: string
  away: string
}

const ROWS: [label: string, key: 'possession' | 'shots' | 'on_target' | 'passes_completed', unit: string][] = [
  ['Possession', 'possession', '%'],
  ['Shots', 'shots', ''],
  ['On target', 'on_target', ''],
  ['Passes completed', 'passes_completed', ''],
]

/** The numbers the stat bars show (a live tick has them, and so do the full-match stats). */
type StatLine = Pick<LiveTick, 'possession' | 'shots' | 'on_target' | 'passes_completed'>

interface LiveStatsProps {
  tick: StatLine | null
  teams: Teams
  label?: string
  children?: ReactNode // shown between the team names and the bars (e.g. the goals)
}

/** Stat bars, computed by code: home on the left, away on the right. Live mode updates them every minute. */
export function LiveStats({ tick, teams, label = 'Live stats', children }: LiveStatsProps) {
  return (
    <section className="live-stats" aria-label={label}>
      <div className="live-stats-teams">
        <span className="home">{teams.home}</span>
        <span className="away">{teams.away}</span>
      </div>
      {children}
      {ROWS.map(([label, key, unit]) => {
        const home = tick?.[key].Home ?? 0
        const away = tick?.[key].Away ?? 0
        const share = home + away ? (100 * home) / (home + away) : 50
        const show = (n: number) => (tick ? `${n}${unit}` : '–') // nothing to show before kick-off
        return (
          <div className={`live-stat stat-${key}`} key={key}>
            <span className="value">{show(home)}</span>
            <div className="live-stat-bar" role="img" aria-label={`${label}: ${show(home)} to ${show(away)}`}>
              <span className="label">{label}</span>
              <span className="bar">
                <span className="home" style={{ width: `${share}%` }} />
                <span className="away" style={{ width: `${100 - share}%` }} />
              </span>
            </div>
            <span className="value">{show(away)}</span>
          </div>
        )
      })}
    </section>
  )
}

const KIND_LABELS: Record<LiveMoment['kind'], string> = {
  goal: 'Goal',
  counterattack: 'Counterattack',
  'half-time': 'Half-time',
  'full-time': 'Full-time',
}

/** The code-made facts for a moment's banner: for a goal, the scorer and the score it made. */
function momentFacts(moment: LiveMoment, events: MatchEvent[], teams: Teams): string {
  const team = (t: Team | null) => (t === 'Home' ? teams.home : t === 'Away' ? teams.away : '')
  if (moment.kind !== 'goal') return team(moment.team)
  const shotId = moment.event_ids[moment.event_ids.length - 1]
  const goals = events.filter((e) => e.type === 'shot' && e.outcome === 'goal' && e.event_id <= shotId)
  const score = `${goals.filter((e) => e.team === 'Home').length}–${goals.filter((e) => e.team === 'Away').length}`
  const scorer = goals[goals.length - 1]?.player ?? ''
  return `${team(moment.team)} · ${scorer} · ${score}`
}

interface LiveFeedProps {
  feed: FeedItem[]
  mode: LiveStart['commentary'] | null
  playing: boolean
  events: MatchEvent[]
  teams: Teams
  selected: RecapSentence | null
  onSelect: (sentence: RecapSentence, item: FeedItem) => void
}

/** Key moments, newest first. Banners come from code instantly; verified commentary follows. */
export function LiveFeed({ feed, mode, playing, events, teams, selected, onSelect }: LiveFeedProps) {
  return (
    <ol className="live-feed" aria-live="polite">
      {feed.map((item) => (
        <li key={item.moment.key} className={`live-item ${item.moment.kind}`}>
          <div className="live-banner">
            <span className="live-minute">{item.moment.minute}'</span>
            <span className="live-kind">{KIND_LABELS[item.moment.kind]}</span>
            <span className="live-facts">{momentFacts(item.moment, events, teams)}</span>
          </div>
          {item.commentary?.sentences.map((s) => (
            <button
              type="button"
              key={s.text}
              className={`sentence${selected === s ? ' selected' : ''}`}
              onClick={() => onSelect(s, item)}
              aria-pressed={selected === s}
            >
              <span className="sentence-text">{s.text}</span>
              <span className="sentence-evidence">
                {evidenceLabel(s)}
                {item.commentary && item.commentary.rewrites > 0 && ' · rewritten after fact-check'}
              </span>
            </button>
          ))}
          {!item.commentary && mode === 'live' && playing && (
            <p className="live-pending">Commentator writing, Verifier checking…</p>
          )}
        </li>
      ))}
    </ol>
  )
}

/** The finished match in one card: the goals, then the same stat bars as live mode. */
export function MatchGlance({ match, stats }: { match: Match; stats: Stats }) {
  const p = stats.get_possession
  const s = stats.get_shots
  const line: StatLine = {
    possession: { Home: p.Home.percent, Away: p.Away.percent },
    shots: { Home: s.Home.total, Away: s.Away.total },
    on_target: { Home: s.Home.on_target, Away: s.Away.on_target },
    passes_completed: { Home: p.Home.passes_completed, Away: p.Away.passes_completed },
  }
  return (
    <LiveStats tick={line} teams={{ home: match.home_team, away: match.away_team }} label="The match at a glance">
      {stats.get_goals.length > 0 && (
        <ol className="glance-goals" aria-label="Goals">
          {stats.get_goals.map((g) => (
            <li key={g.event_id} className={g.team === 'Home' ? 'home' : 'away'}>
              <span className="glance-ball" aria-hidden="true" />
              {g.minute}' {g.player} <span className="muted">{g.score_after}</span>
            </li>
          ))}
        </ol>
      )}
    </LiveStats>
  )
}
