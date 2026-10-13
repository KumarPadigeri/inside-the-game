// Loading placeholders: grey shapes the size of the real content, so switching matches or styles
// fades in smoothly instead of flashing empty states. Hidden from screen readers (the live region says "Loading").

function Bar({ width = '100%', height = 14 }: { width?: string; height?: number }) {
  return <span className="skeleton" style={{ width, height }} />
}

export function MatchListSkeleton() {
  return (
    <ul aria-hidden="true">
      {Array.from({ length: 8 }, (_, i) => (
        <li key={i} className="skeleton-card">
          <Bar width="70%" />
          <Bar width="55%" />
        </li>
      ))}
    </ul>
  )
}

export function ScoreboardSkeleton() {
  return (
    <section className="scoreboard" aria-hidden="true">
      <Bar width="60%" height={18} />
      <Bar width="72px" height={30} />
      <Bar width="60%" height={18} />
    </section>
  )
}

export function RecapSkeleton() {
  return (
    <div className="recap-grid" aria-hidden="true">
      <div className="recap-column skeleton-stack">
        <Bar width="90%" height={24} />
        <Bar width="60%" height={24} />
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="skeleton-stack tight">
            <Bar width={i % 2 ? '85%' : '95%'} />
            <Bar width="35%" height={10} />
          </div>
        ))}
      </div>
      <aside className="skeleton-stack">
        <Bar width="80%" />
        <Bar width="40%" height={10} />
        {Array.from({ length: 5 }, (_, i) => (
          <Bar key={i} height={18} />
        ))}
      </aside>
    </div>
  )
}
