import { useEffect, useRef, type RefObject } from 'react'

/** While `open`, a click outside `root` or the Escape key calls `close` (popover panels and menus). */
export function useDismiss(open: boolean, root: RefObject<HTMLElement | null>, close: () => void) {
  const latest = useRef(close)
  useEffect(() => {
    latest.current = close
  })
  useEffect(() => {
    if (!open) return
    const onPointer = (e: PointerEvent) => !root.current?.contains(e.target as Node) && latest.current()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && latest.current()
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, root])
}
