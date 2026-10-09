import type { MatchEvent } from '../api'

// Pitch drawn at 105 x 68 (metres). Event x/y run 0-100 from the acting team's
// own goal, so we flip Away events: Home always attacks left to right here.
const W = 105
const H = 68

function position(event: MatchEvent): [number, number] {
  const x = event.team === 'Home' ? event.x : 100 - event.x
  const y = event.team === 'Home' ? event.y : 100 - event.y
  return [(x / 100) * W, (y / 100) * H]
}

interface PitchProps {
  events: MatchEvent[]
}

/** The events behind a sentence, in order, joined into the path of the attack. */
export function Pitch({ events }: PitchProps) {
  const points = events.map(position)
  return (
    <svg className="pitch" viewBox={`-2 -2 ${W + 4} ${H + 4}`} role="img" aria-label="Where these events happened">
      <rect className="pitch-grass" x={-2} y={-2} width={W + 4} height={H + 4} rx={2} />
      <g className="pitch-lines">
        <rect x={0} y={0} width={W} height={H} />
        <line x1={W / 2} y1={0} x2={W / 2} y2={H} />
        <circle cx={W / 2} cy={H / 2} r={9.15} />
        <rect x={0} y={(H - 40.3) / 2} width={16.5} height={40.3} />
        <rect x={W - 16.5} y={(H - 40.3) / 2} width={16.5} height={40.3} />
        <rect x={0} y={(H - 18.3) / 2} width={5.5} height={18.3} />
        <rect x={W - 5.5} y={(H - 18.3) / 2} width={5.5} height={18.3} />
      </g>
      {points.length > 1 && (
        <polyline className="pitch-path" points={points.map(([x, y]) => `${x},${y}`).join(' ')} />
      )}
      {events.map((event, i) => {
        const [x, y] = points[i]
        const isGoal = event.type === 'shot' && event.outcome === 'goal'
        return (
          <g key={event.event_id} className={`pitch-event team-${event.team.toLowerCase()}${isGoal ? ' goal' : ''}`}>
            <circle cx={x} cy={y} r={isGoal ? 2.6 : event.type === 'shot' ? 2.1 : 1.6} />
            <text x={x} y={y - 3}>
              {i + 1}
            </text>
            <title>
              {`${event.minute}' ${event.player} ${event.type} (${event.outcome})`}
            </title>
          </g>
        )
      })}
      <text className="pitch-caption" x={W - 1} y={H - 1.5}>
        Home attacks →
      </text>
    </svg>
  )
}
