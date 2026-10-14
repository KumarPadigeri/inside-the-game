import type { RecapSentence, VerifiedRecap } from '../api'
import { evidenceLabel } from '../matchEvents'

interface RecapViewProps {
  result: VerifiedRecap
  selected: RecapSentence | null
  onSelect: (sentence: RecapSentence) => void
}

/** The verified recap. Every sentence is a button: click it to see what proves it. */
export function RecapView({ result, selected, onSelect }: RecapViewProps) {
  const { recap } = result
  const sentence = (s: RecapSentence, headline = false) => (
    <button
      type="button"
      key={s.text}
      className={`sentence${headline ? ' headline' : ''}${selected === s ? ' selected' : ''}`}
      onClick={() => onSelect(s)}
      aria-pressed={selected === s}
    >
      <span className="sentence-text">{s.text}</span>
      <span className="sentence-evidence">{evidenceLabel(s)}</span>
    </button>
  )
  return (
    <article className="recap" lang={recap.language}>
      {sentence(recap.headline, true)}
      {recap.sentences.map((s) => sentence(s))}
    </article>
  )
}

/** What the Verifier sent back (and what it had to remove): the rewrite loop made visible. */
export function FactCheckLog({ result, collapsed = false }: { result: VerifiedRecap; collapsed?: boolean }) {
  const { rewrites, rejections, removed } = result
  return (
    <details className="factcheck" open={!collapsed && rejections.length > 0}>
      <summary>
        Fact-check log:{' '}
        {rewrites === 0
          ? 'every sentence passed on the first draft'
          : `${rejections.length} issue${rejections.length === 1 ? '' : 's'} caught, ${rewrites} rewrite${rewrites === 1 ? '' : 's'}`}
        {removed.length > 0 && `, ${removed.length} removed`}
      </summary>
      {rejections.map((r, i) => (
        <div key={i} className="rejection">
          <div className="rejection-draft">Draft {r.draft + 1}</div>
          <p className="rejection-text">“{r.text}”</p>
          <p className="rejection-problem">{r.problem}</p>
        </div>
      ))}
      {removed.map((r, i) => (
        <div key={`removed-${i}`} className="rejection removed">
          <div className="rejection-draft">Removed</div>
          <p className="rejection-text">“{r.text}”</p>
          <p className="rejection-problem">{r.problem}</p>
        </div>
      ))}
    </details>
  )
}
