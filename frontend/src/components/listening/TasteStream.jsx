import { useMemo, useState } from 'react'
import { stack, stackOffsetWiggle, stackOrderInsideOut, area, curveBasis, scaleLinear } from 'd3'

// Taste drift as flowing bands: each artist is a ribbon that swells while you
// were obsessed and pinches to nothing when you moved on. Wiggle offset (the
// classic streamgraph layout) keeps the mass centred so the shape reads as a
// current rather than a stack sitting on an axis.
const W = 900
const H = 340
const PAD = { top: 12, right: 12, bottom: 26, left: 12 }

const PALETTE = [
  '#3DDC97', '#5AC8FA', '#B08CF8', '#F5C451', '#FF7A9C',
  '#22D3EE', '#FB923C', '#A7F3D0', '#F472B6', '#94A3B8',
]

export default function TasteStream({ series }) {
  const [hover, setHover] = useState(null)
  const { paths, ticks, empty } = useMemo(() => {
    const { rows, artists, months } = series
    if (!rows.length || !artists.length) return { paths: [], ticks: [], empty: true }

    const layers = stack()
      .keys(artists)
      .offset(stackOffsetWiggle)
      .order(stackOrderInsideOut)(rows)

    const x = scaleLinear().domain([0, rows.length - 1]).range([PAD.left, W - PAD.right])
    const lo = Math.min(...layers.flat(2).filter(Number.isFinite))
    const hi = Math.max(...layers.flat(2).filter(Number.isFinite))
    const y = scaleLinear().domain([lo, hi]).range([H - PAD.bottom, PAD.top])

    const gen = area()
      .x((_, i) => x(i))
      .y0(d => y(d[0]))
      .y1(d => y(d[1]))
      .curve(curveBasis)

    const paths = layers.map((layer, i) => {
      // label the month where this artist's band is thickest
      let bestI = 0, bestT = -1
      layer.forEach((d, idx) => { const t = d[1] - d[0]; if (t > bestT) { bestT = t; bestI = idx } })
      const mid = layer[bestI]
      return {
        key: layer.key,
        d: gen(layer),
        color: PALETTE[i % PALETTE.length],
        thickest: bestT,
        labelX: x(bestI),
        labelY: y((mid[0] + mid[1]) / 2),
      }
    })

    // one tick per January, plus the first month
    const ticks = months.map((m, i) => ({ m, i, x: x(i) }))
      .filter(t => t.m.endsWith('-01') || t.i === 0)
      .map(t => ({ ...t, label: t.m.slice(0, 4) }))

    return { paths, ticks, empty: false }
  }, [series])

  if (empty) return <p className="text-sm text-[var(--text-low)]">Not enough months to draw a drift.</p>

  return (
    <div className="listening-stream">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Top artists by listening time across months">
        {paths.map(p => (
          <path key={p.key} d={p.d} fill={p.color}
                opacity={hover == null || hover === p.key ? 0.82 : 0.16}
                onMouseEnter={() => setHover(p.key)}
                onMouseLeave={() => setHover(null)}
                style={{ transition: 'opacity 160ms ease' }} />
        ))}
        {paths.filter(p => p.thickest > 0.6).map(p => (
          <text key={`l-${p.key}`} x={p.labelX} y={p.labelY} textAnchor="middle"
                dominantBaseline="middle" className="listening-stream-label"
                opacity={hover == null || hover === p.key ? 1 : 0.25}>{p.key}</text>
        ))}
        {ticks.map(t => (
          <g key={t.m}>
            <line x1={t.x} x2={t.x} y1={PAD.top} y2={H - PAD.bottom}
                  stroke="var(--hairline)" strokeWidth="1" opacity="0.35" />
            <text x={t.x} y={H - 8} textAnchor="middle" className="listening-stream-tick">{t.label}</text>
          </g>
        ))}
      </svg>
      <div className="listening-stream-key">
        {paths.map(p => (
          <button key={p.key} type="button"
                  onMouseEnter={() => setHover(p.key)} onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(p.key)} onBlur={() => setHover(null)}
                  style={{ opacity: hover == null || hover === p.key ? 1 : 0.4 }}>
            <i style={{ background: p.color }} />{p.key}
          </button>
        ))}
      </div>
    </div>
  )
}
