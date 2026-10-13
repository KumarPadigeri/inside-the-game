// Scrollbars stay hidden until something scrolls: while an element is scrolling it gets the
// "is-scrolling" class (which index.css uses to show its scrollbar), removed shortly after it stops.

const HIDE_AFTER_MS = 900
const timers = new WeakMap<Element, number>()

export function showScrollbarsWhileScrolling() {
  // Scroll events don't bubble, so listen in the capture phase to hear every scroll area.
  document.addEventListener(
    'scroll',
    (event) => {
      const target = event.target instanceof Element ? event.target : document.documentElement
      target.classList.add('is-scrolling')
      window.clearTimeout(timers.get(target))
      timers.set(
        target,
        window.setTimeout(() => target.classList.remove('is-scrolling'), HIDE_AFTER_MS),
      )
    },
    { capture: true, passive: true },
  )
}
