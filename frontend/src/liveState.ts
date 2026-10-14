import { useCallback, useEffect, useRef, useState } from 'react'
import {
  streamLive,
  type Commentary,
  type Language,
  type LiveMessage,
  type LiveMoment,
  type LiveStart,
  type LiveTick,
  type MatchEvent,
  type Style,
} from './api'

// Live mode state, folded from the messages the backend streams minute by minute.

/** A key moment in the feed, with its commentary once the agents (or a saved run) deliver it. */
export interface FeedItem {
  moment: LiveMoment
  commentary: Commentary | null
}

export interface LiveState {
  status: 'idle' | 'playing' | 'done'
  commentary: LiveStart['commentary'] | null
  tick: LiveTick | null // the latest minute
  events: MatchEvent[] // every event so far (the evidence for commentary)
  feed: FeedItem[] // newest first
}

export const IDLE_LIVE: LiveState = { status: 'idle', commentary: null, tick: null, events: [], feed: [] }

export function applyLive(state: LiveState, message: LiveMessage): LiveState {
  switch (message.type) {
    case 'start':
      return { ...IDLE_LIVE, status: 'playing', commentary: message.data.commentary }
    case 'tick':
      return { ...state, tick: message.data, events: [...state.events, ...message.data.events] }
    case 'moment':
      return { ...state, feed: [{ moment: message.data, commentary: null }, ...state.feed] }
    case 'commentary': {
      const line = message.data
      return {
        ...state,
        feed: state.feed.map((item) => (item.moment.key === line.moment.key ? { ...item, commentary: line } : item)),
      }
    }
    case 'done':
      return { ...state, status: 'done' }
  }
}

export interface LiveRequest {
  matchId: string
  style: Style
  language: Language
  generate: boolean // true: the agents commentate now (needs the passcode)
  passcode: string
  secondsPerMinute: number
}

/**
 * One live stream and its state. Start, stop or reset it; a new start (or leaving the page) ends the old one.
 * `start` rejects on failure (e.g. a PasscodeError), but not when the stream was stopped on purpose.
 */
export function useLiveStream() {
  const [state, setState] = useState<LiveState>(IDLE_LIVE)
  const stream = useRef<AbortController | null>(null)

  useEffect(() => () => stream.current?.abort(), [])

  const reset = useCallback(() => {
    stream.current?.abort()
    stream.current = null
    setState(IDLE_LIVE)
  }, [])

  const stop = useCallback(() => {
    stream.current?.abort()
    stream.current = null
    setState((s) => (s.status === 'playing' ? { ...s, status: 'done' } : s))
  }, [])

  const start = useCallback(
    async (request: LiveRequest) => {
      reset()
      const controller = new AbortController()
      stream.current = controller
      try {
        await streamLive(
          request.matchId,
          request.style,
          request.language,
          { ...request, signal: controller.signal },
          (message) => setState((s) => applyLive(s, message)),
        )
      } catch (e) {
        if (controller.signal.aborted) return // stopped on purpose
        setState((s) => ({ ...s, status: 'done' }))
        throw e
      } finally {
        if (stream.current === controller) stream.current = null
      }
    },
    [reset],
  )

  return { state, start, stop, reset }
}
