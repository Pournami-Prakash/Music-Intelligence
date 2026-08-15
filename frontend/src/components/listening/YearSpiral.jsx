import { useMemo, useState } from 'react'
import { formatDuration } from '../../lib/listeningHistory'

// The year as one continuous coil instead of a grid of squares: it starts in
// January at the centre and winds outward, one turn per month, so seasons read
// as bands and a quiet stretch reads as a thinning in the spiral.
const SIZE = 460
const R0 = 44
const R1 = 214
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export default function YearSpiral({ days, year }) {
  const [hover, setHover] = useState(null)

  const { segments } = useMemo(() => {
    const max = Math.max(...days.map(d => d.ms), 1)
    const n = days.length
    const segments = days.map((d, i) => {
      // 12 turns across the year; angle within a turn is position in the month.
      const monthFrac = d.date.getMonth() + (d.date.getDate() - 1) / daysInMonth(d.date)
      const a0 = (monthFrac % 1) * Math.PI * 2 - Math.PI / 2
      const a1 = a0 + (1 / daysInMonth(d.date)) * Math.PI * 2
      const rBase = R0 + (R1 - R0) * (i / n)
      const t = d.ms / max
      const thick = 2 + t * 13
      return {
        ...d,
        i,
        d: ringSegment(rBase, rBase + thick, a0, a1),
        t,
      }
    })
    return { segments }
  }, [days])

  const active = hover != null ? segments[hover] : null
  const total = days.reduce((a, b) => a + b.ms, 0)

  return (
    <div className="listening-spiral">
      <svg viewBox={`${-SIZE / 2} ${-SIZE / 2} ${SIZE} ${SIZE}`} role="img"
           aria-label={`Daily listening through ${year}, drawn as an outward spiral`}>
        {segments.map(s => (
          <path key={s.key} d={s.d}
                fill={s.ms ? 'var(--route-accent)' : 'var(--hairline)'}
                opacity={s.ms ? 0.22 + s.t * 0.78 : 0.5}
                onMouseEnter={() => setHover(s.i)}
                onMouseLeave={() => setHover(null)} />
        ))}
        {MONTHS.map((m, i) => {
          const a = (i / 12) * Math.PI * 2 - Math.PI / 2
          const r = R1 + 22
          return (
            <text key={m} x={Math.cos(a) * r} y={Math.sin(a) * r}
                  textAnchor="middle" dominantBaseline="middle"
                  className="listening-spiral-tick">{m}</text>
          )
        })}
        <text textAnchor="middle" y={-4} className="listening-spiral-center-value">
          {active ? formatDuration(active.ms) : year}
        </text>
        <text textAnchor="middle" y={18} className="listening-spiral-center-label">
          {active
            ? active.date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
            : formatDuration(total)}
        </text>
      </svg>
    </div>
  )
}

function daysInMonth(d) {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()
}

function ringSegment(r0, r1, a0, a1) {
  const p = (r, a) => `${(Math.cos(a) * r).toFixed(2)} ${(Math.sin(a) * r).toFixed(2)}`
  const large = a1 - a0 > Math.PI ? 1 : 0
  return [
    `M ${p(r0, a0)}`,
    `A ${r0} ${r0} 0 ${large} 1 ${p(r0, a1)}`,
    `L ${p(r1, a1)}`,
    `A ${r1} ${r1} 0 ${large} 0 ${p(r1, a0)}`,
    'Z',
  ].join(' ')
}
