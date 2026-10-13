import type { MatchEvent } from '../api'

// Pitch drawn at 105 x 68 (metres). Event x/y run 0-100 from the acting team's
// own goal, so we flip Away events: Home always attacks left to right here.
const W = 105
const H = 68

// Ball replay timing, in seconds.
const SECONDS_PER_PASS = 0.45
const PAUSE_BETWEEN_MOVES = 0.7

type Point = [number, number]

function position(event: MatchEvent): Point {
  const x = event.team === 'Home' ? event.x : 100 - event.x
  const y = event.team === 'Home' ? event.y : 100 - event.y
  return [(x / 100) * W, (y / 100) * H]
}

const isGoal = (event: MatchEvent) => event.type === 'shot' && event.outcome === 'goal'

/** Split the events into moves (one per possession), keeping each event's number on the pitch. */
function moves(events: MatchEvent[]): { points: Point[]; goal: boolean }[] {
  const result: { possession: number; points: Point[]; goal: boolean }[] = []
  for (const event of events) {
    const last = result[result.length - 1]
    if (last && last.possession === event.possession_id) {
      last.points.push(position(event))
      last.goal = isGoal(event)
    } else {
      result.push({ possession: event.possession_id, points: [position(event)], goal: isGoal(event) })
    }
  }
  return result
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

const pathOf = (points: Point[]) => points.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${y}`).join(' ')

interface PitchProps {
  events: MatchEvent[]
  /** Change this number to play the ball replay again. */
  replay?: number
  /** Live mode: the latest minute's moves, no numbers or replay; the ball sits where play is now. */
  live?: boolean
}

/**
 * The events behind a sentence, numbered in order and joined into the path of each attack.
 * A ball then replays each move (SVG animation), with a pulse where a goal was scored.
 */
export function Pitch({ events, replay = 0, live = false }: PitchProps) {
  const points = events.map(position)
  const groups = moves(events)
  const animate = !live && !prefersReducedMotion() && events.length > 0

  // When each move starts, so the moves play one after another.
  let clock = 0.3
  const timeline = groups.map((group) => {
    const duration = Math.max(0.4, (group.points.length - 1) * SECONDS_PER_PASS)
    const entry = { ...group, start: clock, duration }
    clock += duration + PAUSE_BETWEEN_MOVES
    return entry
  })

  return (
    // A new key restarts the SVG's animation clock: on a new sentence, or when Replay is pressed.
    <svg
      key={`${events.map((e) => e.event_id).join('-')}#${replay}`}
      className="pitch"
      viewBox={`-2 -2 ${W + 4} ${H + 4}`}
      role="img"
      aria-label="Where these events happened"
    >
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
      {groups
        .filter((group) => group.points.length > 1)
        .map((group, i) => (
          <polyline key={i} className="pitch-path" points={group.points.map(([x, y]) => `${x},${y}`).join(' ')} />
        ))}
      {events.map((event, i) => {
        const [x, y] = points[i]
        return (
          <g
            key={event.event_id}
            className={`pitch-event team-${event.team.toLowerCase()}${isGoal(event) ? ' goal' : ''}`}
          >
            <circle cx={x} cy={y} r={isGoal(event) ? 2.6 : event.type === 'shot' ? 2.1 : 1.6} />
            {/* Number above the dot, or below it when the dot is near the top touchline. */}
            {!live && (
              <text x={x} y={y < 5 ? y + 5.2 : y - 3}>
                {i + 1}
              </text>
            )}
            <title>{`${event.minute}' ${event.player} ${event.type} (${event.outcome})`}</title>
          </g>
        )
      })}
      {animate &&
        timeline.map((move, i) => {
          const [endX, endY] = move.points[move.points.length - 1]
          const end = move.start + move.duration
          const isLastMove = i === timeline.length - 1
          return (
            <g key={`move-${i}`} aria-hidden="true">
              {move.goal && (
                <circle className="pitch-goal-pulse" cx={endX} cy={endY} r={2} opacity={0}>
                  <animate attributeName="r" values="2;7" begin={`${end}s`} dur="0.8s" repeatCount={2} />
                  <animate attributeName="opacity" values="0.9;0" begin={`${end}s`} dur="0.8s" repeatCount={2} />
                </circle>
              )}
              {/* The ball sits at (0,0) and is moved along the path; hidden until its move starts. */}
              <circle className="pitch-ball" r={1.4} opacity={0}>
                <set attributeName="opacity" to="1" begin={`${move.start}s`} />
                <animateMotion
                  path={pathOf(move.points)}
                  begin={`${move.start}s`}
                  dur={`${move.duration}s`}
                  fill="freeze"
                />
                {!isLastMove && <set attributeName="opacity" to="0" begin={`${end + PAUSE_BETWEEN_MOVES - 0.05}s`} />}
              </circle>
            </g>
          )
        })}
      {live && points.length > 0 && (
        <circle className="pitch-ball" cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r={1.4} />
      )}
      <text className="pitch-caption" x={W - 1} y={H - 1.5}>
        Home attacks →
      </text>
    </svg>
  )
}
