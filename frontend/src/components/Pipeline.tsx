import type { PipelineState, StepStatus } from '../pipelineState'

// [name, one-line role shown in the box, fuller explanation shown on hover]
const LABELS: Record<string, [string, string, string]> = {
  analyst: [
    'Analyst',
    'calls the stats tools',
    'Finds what mattered using Python stats tools. Never does the maths itself.',
  ],
  retrieval: ['Retrieval', 'vector search in Cosmos DB', 'Finds similar moments in other matches with vector search.'],
  narrator: ['Narrator', 'writes the recap', 'Writes in the chosen voice, citing a finding for every sentence.'],
  verifier: [
    'Verifier',
    'fact-checks every sentence',
    'Checks each sentence against its evidence; sends failures back.',
  ],
}

function Step({ id, status, note }: { id: string; status: StepStatus; note?: string }) {
  const [label, role, explanation] = LABELS[id]
  return (
    // Focusable so keyboard users can open the tooltip too.
    <div className={`step step-${status}`} data-tooltip={explanation} tabIndex={0}>
      <span className="step-dot" aria-hidden="true" />
      <div>
        <div className="step-label">{label}</div>
        <div className="step-role">{note ?? role}</div>
        <span className="visually-hidden">{explanation}</span>
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
      <span className="pipeline-arrow" aria-hidden="true">
        →
      </span>
      <Step id="narrator" status={steps.narrator} note={rewrites ? `rewrite ${rewrites}` : undefined} />
      <span className="pipeline-arrow loop" aria-hidden="true" title="Rejected sentences go back for a rewrite">
        ⇄
      </span>
      <Step id="verifier" status={steps.verifier} />
    </div>
  )
}
