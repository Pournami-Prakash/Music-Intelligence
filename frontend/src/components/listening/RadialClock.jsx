import { useMemo, useState } from 'react'
import { arc as d3arc } from 'd3'
import { formatDuration, formatHour } from '../../lib/listeningHistory'

// A 24-hour dial rather than a bar chart: midnight at the top, each hour a
// wedge whose reach is how long you listened in it. Weekday and weekend are
// drawn as two concentric bands so the shift between them is a shape, not a
// legend you have to read.
const SIZE = 460
const R_OUTER = 206
const R_INNER = 62
const GAP = 0.012

export default function RadialClock({ byHour, byHourPlays }) {
  const [hover, setHover] = useState(null)

  const { wedges, totals } = useMemo(() => {
    const max = Math.max(...byHour.weekday, ...byHour.weekend, 1)
    const band = (R_OUTER - R_INNER) / 2
    const wedges = []
    for (let h = 0; h < 24; h += 1) {
      const a0 = (h / 24) * Math.PI * 2 + GAP
      const a1 = ((h + 1) / 24) * Math.PI * 2 - GAP
      wedges.push({
        hour: h,
        weekday: {
          d: d3arc()({
            innerRadius: R_INNER,
            outerRadius: R_INNER + band * (byHour.weekday[h] / max),
            startAngle: a0, endAngle: a1,
          }),
          ms: byHour.weekday[h], plays: byHourPlays.weekday[h],
        },
        weekend: {
          d: d3arc()({
            innerRadius: R_INNER + band,
            outerRadius: R_INNER + band + band * (byHour.weekend[h] / max),
            startAngle: a0, endAngle: a1,
          }),
          ms: byHour.weekend[h], plays: byHourPlays.weekend[h],
        },
      })
    }
    return {
      wedges,
      totals: {
        weekday: byHour.weekday.reduce((a, b) => a + b, 0),
        weekend: byHour.weekend.reduce((a, b) => a + b, 0),
      },
    }
  }, [byHour, byHourPlays])

  const active = hover != null ? wedges[hover] : null

  return (
    <div className="listening-clock">
      <svg viewBox={`${-SIZE / 2} ${-SIZE / 2} ${SIZE} ${SIZE}`} role="img"
           aria-label="Listening time by hour of day, weekday and weekend compared">
        <g transform="rotate(-90)">
          {/* guide rings at 1/3 and 2/3 of peak */}
          {[0.33, 0.66, 1].map(f => (
            <circle key={f} r={R_INNER + ((R_OUTER - R_INNER) / 2) * f} fill="none"
                    stroke="var(--hairline)" strokeWidth="1" opacity="0.5" />
          ))}
          <circle r={R_INNER + (R_OUTER - R_INNER) / 2} fill="none"
                  stroke="var(--hairline)" strokeWidth="1" />

          {wedges.map(w => (
            <g key={w.hour}
               onMouseEnter={() => setHover(w.hour)}
               onMouseLeave={() => setHover(null)}>
              {/* hit area so thin wedges stay hoverable */}
              <path d={d3arc()({ innerRadius: R_INNER, outerRadius: R_OUTER,
                                 startAngle: (w.hour / 24) * Math.PI * 2,
                                 endAngle: ((w.hour + 1) / 24) * Math.PI * 2 })}
                    fill="transparent" />
              <path d={w.weekday.d} fill="var(--route-accent)"
                    opacity={hover == null || hover === w.hour ? 0.85 : 0.28}
                    style={{ transition: 'opacity 160ms ease' }} />
              <path d={w.weekend.d} fill="var(--text-hi)"
                    opacity={hover == null || hover === w.hour ? 0.42 : 0.14}
                    style={{ transition: 'opacity 160ms ease' }} />
            </g>
          ))}
        </g>

        {/* hour ticks every 3h, upright */}
        {[0, 3, 6, 9, 12, 15, 18, 21].map(h => {
          const a = (h / 24) * Math.PI * 2 - Math.PI / 2
          const r = R_OUTER + 18
          return (
            <text key={h} x={Math.cos(a) * r} y={Math.sin(a) * r}
                  textAnchor="middle" dominantBaseline="middle"
                  className="listening-clock-tick">{formatHour(h)}</text>
          )
        })}

        <text textAnchor="middle" y={-6} className="listening-clock-center-value">
          {active ? formatHour(active.hour) : formatHour(peakHour(byHour))}
        </text>
        <text textAnchor="middle" y={16} className="listening-clock-center-label">
          {active
            ? `${formatDuration(active.weekday.ms + active.weekend.ms)}`
            : 'peak hour'}
        </text>
      </svg>

      <div className="listening-clock-key">
        <span><i style={{ background: 'var(--route-accent)', opacity: 0.85 }} />Weekday · {formatDuration(totals.weekday)}</span>
        <span><i style={{ background: 'var(--text-hi)', opacity: 0.42 }} />Weekend · {formatDuration(totals.weekend)}</span>
      </div>
    </div>
  )
}

function peakHour(byHour) {
  let best = 0, bestMs = -1
  for (let h = 0; h < 24; h += 1) {
    const ms = byHour.weekday[h] + byHour.weekend[h]
    if (ms > bestMs) { bestMs = ms; best = h }
  }
  return best
}
