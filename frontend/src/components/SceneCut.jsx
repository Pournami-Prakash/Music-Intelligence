import { useEffect, useRef } from 'react'
import { animate as anime, stagger } from 'animejs'

export default function SceneCut({ scene }) {
  const rootRef = useRef(null)

  useEffect(() => {
    const root = rootRef.current
    if (!root || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined

    root.style.removeProperty('opacity')
    root.classList.remove('is-active')
    void root.offsetWidth
    root.classList.add('is-active')
    const bars = root.querySelectorAll('.scene-cut-bar')
    const animations = [
      anime(bars, {
        scaleX: [0, 1, 0],
        delay: stagger(24),
        duration: 460,
        ease: 'inOutQuart',
      }),
    ]
    return () => {
      root.classList.remove('is-active')
      animations.forEach(animation => animation?.cancel?.())
    }
  }, [scene.key])

  return (
    <div className="scene-cut" ref={rootRef} aria-hidden="true">
      <div className="scene-cut-bars">
        <i className="scene-cut-bar" />
        <i className="scene-cut-bar" />
        <i className="scene-cut-bar" />
      </div>
    </div>
  )
}
