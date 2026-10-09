import type { PipelineState, StepStatus } from '../pipelineState'

const LABELS: Record<string, [string, string]> = {
  analyst: ['Analyst', 'calls the stats tools'],
  retrieval: ['Retrieval', 'vector search in Cosmos DB'],
  narrator: ['Narrator', 'writes the recap'],
  verifier: ['Verifier', 'fact-checks every sentence'],
}

function Step({ id, status, note }: { id: string; status: StepStatus; note?: string }) {
  const [label, role] = LABELS[id]
  return (
    <div className={`step step-${status}`}>
      <span className="step-dot" aria-hidden="true" />
      <div>
        <div className="step-label">{label}</div>
        <div className="step-role">{note ?? role}</div>
      </div>
    </div>
  )
}

/** Analyst and Retrieval run in parallel, then Narrator and Verifier loop until every sentence is proven. */
export function Pipeline({ state }: { state: PipelineState }) {
  const { steps, rewrites } = state
  return (
    <div className="pipeline" aria-label="Agent pipeline">
      <div className="pipeline-parallel">
        <Step id="analyst" status={steps.analyst} />
        <Step id="retrieval" status={steps.retrieval} />
      </div>
      <span className="pipeline-arrow" aria-hidden="true">→</span>
      <Step id="narrator" status={steps.narrator} note={rewrites ? `rewrite ${rewrites}` : undefined} />
      <span className="pipeline-arrow loop" aria-hidden="true" title="Rejected sentences go back for a rewrite">
        ⇄
      </span>
      <Step id="verifier" status={steps.verifier} />
    </div>
  )
}
