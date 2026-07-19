import { useEffect, useState } from 'react'
import LottieImport from 'lottie-react'

// Vite's CJS interop can double-nest the default export (default.default is the
// actual component). Resolve it defensively so this works across bundlers.
const Lottie = LottieImport?.default ?? LottieImport

/**
 * Renders a Lottie animation fetched at runtime from /public/assets.
 * Fetching (rather than importing) keeps the large JSON out of the JS bundle
 * and lets heavy animations load only when their page mounts.
 */
export default function LottiePlayer({ src, loop = true, autoplay = true, className, style }) {
  const [data, setData] = useState(null)
  const [reduceMotion, setReduceMotion] = useState(false)

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduceMotion(media.matches)
    update()
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [])

  useEffect(() => {
    let alive = true
    setData(null)
    fetch(src)
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (alive) setData(d) })
      .catch(() => {})
    return () => { alive = false }
  }, [src])

  if (!data) return <div className={className} style={style} aria-hidden="true" />
  return (
    <div aria-hidden="true" className={className} style={style}>
      <Lottie animationData={data} loop={reduceMotion ? false : loop} autoplay={reduceMotion ? false : autoplay} />
    </div>
  )
}
