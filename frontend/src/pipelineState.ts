import type { Progress } from './api'

// Pipeline progress, folded from the events the backend streams while the agents run.

export type StepStatus = 'idle' | 'running' | 'done'

export interface PipelineState {
  steps: Record<string, StepStatus>
  rewrites: number
}

export const EMPTY_PIPELINE: PipelineState = {
  steps: { analyst: 'idle', retrieval: 'idle', narrator: 'idle', verifier: 'idle' },
  rewrites: 0,
}

/** Fold one streamed progress event into the pipeline state. */
export function applyProgress(state: PipelineState, progress: Progress): PipelineState {
  if (!(progress.step in state.steps)) return state // e.g. the "start" step
  const rewrite = /^rewrite (\d+)$/.exec(progress.detail)
  return {
    steps: { ...state.steps, [progress.step]: progress.status === 'started' ? 'running' : 'done' },
    rewrites: rewrite ? Number(rewrite[1]) : state.rewrites,
  }
}
