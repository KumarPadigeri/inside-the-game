import type { Commentary, LiveMessage, LiveMoment, LiveStart, LiveTick, MatchEvent } from './api'

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
