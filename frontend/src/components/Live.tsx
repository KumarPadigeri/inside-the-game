import type { LiveMoment, LiveStart, LiveTick, MatchEvent, RecapSentence, Team } from '../api'
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

/** Running stats, recomputed by code every match minute: home on the left, away on the right. */
export function LiveStats({ tick, teams }: { tick: LiveTick | null; teams: Teams }) {
  return (
    <section className="live-stats" aria-label="Live stats">
      <div className="live-stats-teams">
        <span className="home">{teams.home}</span>
        <span className="away">{teams.away}</span>
      </div>
      {ROWS.map(([label, key, unit]) => {
        const home = tick?.[key].Home ?? 0
        const away = tick?.[key].Away ?? 0
        const share = home + away ? (100 * home) / (home + away) : 50
        return (
          <div className="live-stat" key={key}>
            <span className="value">
              {home}
              {unit}
            </span>
            <div className="live-stat-bar" role="img" aria-label={`${label}: ${home}${unit} to ${away}${unit}`}>
              <span className="label">{label}</span>
              <span className="bar">
                <span className="home" style={{ width: `${share}%` }} />
                <span className="away" style={{ width: `${100 - share}%` }} />
              </span>
            </div>
            <span className="value">
              {away}
              {unit}
            </span>
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
