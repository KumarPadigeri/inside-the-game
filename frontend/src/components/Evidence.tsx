import type { Comparison, Match, MatchEvent, RecapSentence, Stats, Team } from '../api'
import { sentenceEvents } from '../matchEvents'

interface EvidenceProps {
  sentence: RecapSentence
  match: Match
  stats: Stats | null
  comparisons: Comparison[]
  /** Live commentary: the stats are as they stood at this minute, not at full time. */
  asOfMinute?: number
}

const teamName = (match: Match, team: Team) => (team === 'Home' ? match.home_team : match.away_team)

function EventTable({ events, match }: { events: MatchEvent[]; match: Match }) {
  return (
    <table className="events">
      <thead>
        <tr>
          <th>#</th>
          <th>Min</th>
          <th>Team</th>
          <th>Player</th>
          <th>Event</th>
          <th>Outcome</th>
        </tr>
      </thead>
      <tbody>
        {events.map((e, i) => (
          <tr key={e.event_id} className={e.type === 'shot' && e.outcome === 'goal' ? 'goal-row' : undefined}>
            <td>{i + 1}</td>
            <td>{e.minute}'</td>
            <td>{teamName(match, e.team)}</td>
            <td>{e.player}</td>
            <td>{e.type}</td>
            <td>{e.outcome}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function SideBySide({ match, rows }: { match: Match; rows: [string, string | number, string | number][] }) {
  return (
    <table className="stat-table">
      <thead>
        <tr>
          <th />
          <th>{match.home_team}</th>
          <th>{match.away_team}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, home, away]) => (
          <tr key={label}>
            <th scope="row">{label}</th>
            <td>{home}</td>
            <td>{away}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** The tool result a sentence cites, shown the way the agents saw it. */
function ToolEvidence({ tool, match, stats, comparisons, sentence, asOfMinute }: { tool: string } & EvidenceProps) {
  if (tool === 'find_similar_moments') {
    const relevant = comparisons.filter((c) => c.event_ids.some((id) => sentence.event_ids.includes(id)))
    return (
      <section>
        <h4>Similar moments in other matches</h4>
        <p className="muted">Found by vector search over moment embeddings in Cosmos DB.</p>
        {(relevant.length ? relevant : comparisons).map((c) => (
          <div key={c.moment.moment_id} className="comparison">
            <p className="comparison-this">
              <strong>This match, {c.moment.minute}':</strong> {c.moment.description}
            </p>
            <ul>
              {c.similar.map((s) => (
                <li key={s.moment_id}>
                  <strong>
                    {s.home_team} v {s.away_team}, {s.minute}'
                  </strong>{' '}
                  <span className="similarity">{Math.round(s.similarity * 100)}% similar</span>
                  <br />
                  {s.description}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    )
  }
  if (!stats) return null
  switch (tool) {
    case 'get_match_info': {
      const { final_score: score } = stats.get_match_info
      return (
        <section>
          <h4>{asOfMinute === undefined ? 'Final score' : `Score at ${asOfMinute}'`}</h4>
          <p className="big-score">
            {match.home_team} {score.Home} – {score.Away} {match.away_team}
          </p>
        </section>
      )
    }
    case 'get_possession': {
      const p = stats.get_possession
      return (
        <section>
          <h4>Possession (share of passes)</h4>
          <div className="possession-bar" aria-hidden="true">
            <span style={{ width: `${p.Home.percent}%` }} />
          </div>
          <SideBySide
            match={match}
            rows={[
              ['Possession', `${p.Home.percent}%`, `${p.Away.percent}%`],
              ['Passes attempted', p.Home.passes_attempted, p.Away.passes_attempted],
              ['Passes completed', p.Home.passes_completed, p.Away.passes_completed],
              ['Pass accuracy', `${p.Home.pass_accuracy}%`, `${p.Away.pass_accuracy}%`],
            ]}
          />
        </section>
      )
    }
    case 'get_shots': {
      const s = stats.get_shots
      return (
        <section>
          <h4>Shots</h4>
          <SideBySide
            match={match}
            rows={[
              ['Total', s.Home.total, s.Away.total],
              ['On target', s.Home.on_target, s.Away.on_target],
              ['Goals', s.Home.goals, s.Away.goals],
              ['Saved', s.Home.saved, s.Away.saved],
              ['Missed', s.Home.missed, s.Away.missed],
              ['Blocked', s.Home.blocked, s.Away.blocked],
            ]}
          />
        </section>
      )
    }
    case 'get_goals':
      return (
        <section>
          <h4>Goals</h4>
          <ol className="plain-list">
            {stats.get_goals.map((g) => (
              <li key={g.event_id}>
                {g.minute}' {g.player} ({teamName(match, g.team)}) — {g.score_after}
              </li>
            ))}
          </ol>
        </section>
      )
    case 'get_counterattacks':
      return (
        <section>
          <h4>Counterattacks</h4>
          <p className="muted">Ball won in own half, then a shot within 4 passes.</p>
          <ol className="plain-list">
            {stats.get_counterattacks.map((c) => (
              <li key={c.possession_id}>
                {c.minute}' {teamName(match, c.team)}: {c.won_by}, {c.passes} passes, shot {c.outcome}
              </li>
            ))}
          </ol>
        </section>
      )
    case 'get_player_stats': {
      const p = stats.get_player_stats
      if (!p) return null
      return (
        <section>
          <h4>
            {p.player} ({teamName(match, p.team)}), minutes {p.first_minute}–{p.last_minute}
          </h4>
          <table className="stat-table">
            <tbody>
              {(
                [
                  ['Goals', p.goals.map((g) => `${g.minute}' (${g.score_after})`).join(', ') || '0'],
                  ['Shots (on target)', `${p.shots} (${p.shots_on_target})`],
                  ['Passes completed', `${p.passes_completed} of ${p.passes_attempted} (${p.pass_accuracy}%)`],
                  ['Tackles won', p.tackles_won],
                  ['Interceptions won', p.interceptions_won],
                  ['Teammates’ goals set up', p.set_up_goals.map((g) => `${g.minute}'`).join(', ') || '0'],
                  ['Counterattacks', p.counterattacks.map((c) => `${c.minute}' (${c.outcome})`).join(', ') || '0'],
                ] as [string, string | number][]
              ).map(([label, value]) => (
                <tr key={label}>
                  <th scope="row">{label}</th>
                  <td>{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )
    }
    default:
      return null
  }
}

/**
 * Everything that proves one sentence (its events are drawn on the pitch in the sticky band above).
 * The quote stays pinned; the event table and the cited tool results scroll in their own area.
 */
export function Evidence(props: EvidenceProps) {
  const { sentence, match } = props
  const events = sentenceEvents(match, sentence)
  return (
    <div className="evidence">
      <div className="evidence-pinned">
        <p className="evidence-quote">“{sentence.text}”</p>
        {props.asOfMinute !== undefined && (
          <p className="muted evidence-asof">Evidence as it stood at minute {props.asOfMinute}: nothing later.</p>
        )}
      </div>
      <div className="evidence-scroll">
        {events.length > 0 && (
          <section>
            <h4>
              {events.length} event{events.length === 1 ? '' : 's'} behind this sentence
            </h4>
            <EventTable events={events} match={match} />
          </section>
        )}
        {sentence.tools.map((tool) => (
          <ToolEvidence key={tool} tool={tool} {...props} />
        ))}
      </div>
    </div>
  )
}
