import { useEffect, useRef } from 'react'

/*
 * LiquidRibbon — a high-gloss, liquid-chrome ribbon wave that undulates across
 * the lower third of a pitch-black stage. Pure 2D canvas: stacked flowing sine
 * ribbons filled with a drifting metallic gradient, screen-blended for a wet,
 * self-lit sheen. Motion is continuous/periodic, so the loop is seamless with
 * no start/end seam. Honours prefers-reduced-motion by painting one still frame.
 *
 * Palette bridges the atlas green into cobalt / ultraviolet / magenta / amber —
 * the "flowing metallic" look, kept in the brand's key.
 */

// Looped color rings (RGB). paletteAt() wraps, so colors drift forever.
const RIBBONS = [
  {
    palette: [[59, 220, 151], [40, 190, 200], [70, 120, 246], [150, 100, 248], [232, 92, 170]],
    amp: 0.16, base: 0.62, freq: 1.4, speed: 0.06, drift: 0.045, alpha: 0.5, blur: 34, phase: 0,
  },
  {
    palette: [[150, 100, 248], [232, 92, 170], [255, 138, 76], [246, 205, 92], [59, 220, 151]],
    amp: 0.13, base: 0.74, freq: 1.9, speed: -0.045, drift: 0.06, alpha: 0.42, blur: 30, phase: 2.1,
  },
  {
    palette: [[223, 255, 236], [180, 220, 255], [214, 190, 255], [255, 224, 190]],
    amp: 0.1, base: 0.86, freq: 2.6, speed: 0.08, drift: 0.09, alpha: 0.32, blur: 18, phase: 4.3,
  },
]

function paletteAt(palette, u) {
  const n = palette.length
  const x = ((u % 1) + 1) % 1 * n
  const i = Math.floor(x)
  const f = x - i
  const a = palette[i % n]
  const b = palette[(i + 1) % n]
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * f)},${Math.round(a[1] + (b[1] - a[1]) * f)},${Math.round(a[2] + (b[2] - a[2]) * f)})`
}

export default function LiquidRibbon() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined
    const ctx = canvas.getContext('2d')
    if (!ctx) return undefined

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let w = 0
    let h = 0
    let dpr = 1

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = Math.max(1, Math.round(rect.width))
      h = Math.max(1, Math.round(rect.height))
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const draw = (t) => {
      ctx.clearRect(0, 0, w, h)
      ctx.globalCompositeOperation = 'screen'
      const step = Math.max(6, Math.floor(w / 120))

      for (const r of RIBBONS) {
        const grad = ctx.createLinearGradient(0, 0, w, 0)
        const stops = 6
        for (let s = 0; s <= stops; s++) {
          grad.addColorStop(s / stops, paletteAt(r.palette, s / stops + t * r.drift + r.phase))
        }
        ctx.beginPath()
        ctx.moveTo(0, h)
        for (let x = 0; x <= w; x += step) {
          const u = x / w
          const y = h * (
            r.base
            + r.amp * Math.sin(u * Math.PI * r.freq + t * r.speed * 6 + r.phase)
            + r.amp * 0.4 * Math.sin(u * Math.PI * r.freq * 2.3 - t * r.speed * 3.7)
          )
          ctx.lineTo(x, y)
        }
        ctx.lineTo(w, h)
        ctx.closePath()
        ctx.globalAlpha = r.alpha
        ctx.shadowColor = paletteAt(r.palette, t * r.drift + r.phase)
        ctx.shadowBlur = r.blur
        ctx.fillStyle = grad
        ctx.fill()

        // High-gloss crest: a thin bright line riding the wave's top edge.
        ctx.beginPath()
        for (let x = 0; x <= w; x += step) {
          const u = x / w
          const y = h * (
            r.base
            + r.amp * Math.sin(u * Math.PI * r.freq + t * r.speed * 6 + r.phase)
            + r.amp * 0.4 * Math.sin(u * Math.PI * r.freq * 2.3 - t * r.speed * 3.7)
          )
          if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
        }
        ctx.globalAlpha = r.alpha * 0.9
        ctx.lineWidth = 1.4
        ctx.shadowBlur = r.blur * 0.5
        ctx.strokeStyle = paletteAt(r.palette, t * r.drift + r.phase + 0.5)
        ctx.stroke()
      }
      ctx.globalAlpha = 1
      ctx.shadowBlur = 0
      ctx.globalCompositeOperation = 'source-over'
    }

    resize()
    window.addEventListener('resize', resize)

    if (reduce) {
      draw(0)
      return () => window.removeEventListener('resize', resize)
    }

    const start = performance.now()
    const loop = (now) => {
      draw((now - start) / 1000)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return <canvas ref={canvasRef} className="pv-liquid-ribbon" aria-hidden="true" />
}
