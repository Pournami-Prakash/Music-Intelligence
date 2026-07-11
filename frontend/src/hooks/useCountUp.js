import { useEffect, useRef, useState } from 'react'

const prefersReduced = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/**
 * Animate a number from 0 up to `target` with an ease-out cubic curve.
 * Re-runs whenever `target` changes. Honours prefers-reduced-motion by
 * snapping straight to the final value.
 */
export function useCountUp(target, { duration = 1100, decimals = 0 } = {}) {
  const goal = Number(target) || 0
  const [value, setValue] = useState(prefersReduced() ? goal : 0)
  const raf = useRef(0)

  useEffect(() => {
    if (prefersReduced()) { setValue(goal); return }
    const start = performance.now()
    const tick = now => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setValue(goal * eased)
      if (t < 1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [goal, duration])

  const factor = 10 ** decimals
  return Math.round(value * factor) / factor
}
