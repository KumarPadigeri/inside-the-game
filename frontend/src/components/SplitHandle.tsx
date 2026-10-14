import type { KeyboardEvent, PointerEvent, RefObject } from 'react'

export const SPLIT_DEFAULT = 60 // recap side, in percent
const SPLIT_MIN = 35
const SPLIT_MAX = 70
const GAP = 20 // px between the two columns (matches the grid gap in index.css)

const clamp = (value: number) => Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, Math.round(value)))

interface SplitHandleProps {
  split: number
  onChange: (split: number) => void
  container: RefObject<HTMLElement | null>
}

/**
 * The divider between the recap (left) and its evidence (right). Drag it, or focus it and use the
 * arrow keys, to give one side more room; double-click resets it. The pitch above follows the same split.
 */
export function SplitHandle({ split, onChange, container }: SplitHandleProps) {
  function splitAt(clientX: number) {
    const box = container.current?.getBoundingClientRect()
    if (!box) return
    onChange(clamp(((clientX - box.left - GAP / 2) / (box.width - GAP)) * 100))
  }

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) splitAt(e.clientX)
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'ArrowLeft') onChange(clamp(split - 2))
    else if (e.key === 'ArrowRight') onChange(clamp(split + 2))
    else if (e.key === 'Home') onChange(SPLIT_DEFAULT)
    else return
    e.preventDefault()
  }

  return (
    <div
      className="split-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the recap and the evidence"
      aria-valuemin={SPLIT_MIN}
      aria-valuemax={SPLIT_MAX}
      aria-valuenow={split}
      tabIndex={0}
      title="Drag to resize · double-click to reset"
      style={{ left: `calc((100% - ${GAP}px) * ${split / 100} + ${GAP / 2}px)` }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onDoubleClick={() => onChange(SPLIT_DEFAULT)}
      onKeyDown={onKeyDown}
    />
  )
}
