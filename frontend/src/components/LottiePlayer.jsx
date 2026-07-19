import { lazy, Suspense, useEffect, useState } from 'react'
import LottieImport from 'lottie-react'

const DotLottie = lazy(() => import('@lottiefiles/dotlottie-react').then(module => ({ default: module.DotLottieReact })))

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
  const isDotLottie = src?.toLowerCase().endsWith('.lottie')

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduceMotion(media.matches)
    update()
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [])

  useEffect(() => {
    if (isDotLottie) return undefined
    let alive = true
    setData(null)
    fetch(src)
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (alive) setData(d) })
      .catch(() => {})
    return () => { alive = false }
  }, [src, isDotLottie])

  const classes = `atlas-lottie ${className || ''}`.trim()
  if (isDotLottie) {
    return (
      <div aria-hidden="true" className={classes} data-lottie={src} style={style}>
        <Suspense fallback={null}>
          <DotLottie
            src={src}
            loop={reduceMotion ? false : loop}
            autoplay={reduceMotion ? false : autoplay}
            renderConfig={{ autoResize: true }}
            style={{ width: '100%', height: '100%' }}
          />
        </Suspense>
      </div>
    )
  }
  if (!data) return <div className={classes} data-lottie={src} style={style} aria-hidden="true" />
  return (
    <div aria-hidden="true" className={classes} data-lottie={src} style={style}>
      <Lottie animationData={data} loop={reduceMotion ? false : loop} autoplay={reduceMotion ? false : autoplay} />
    </div>
  )
}
