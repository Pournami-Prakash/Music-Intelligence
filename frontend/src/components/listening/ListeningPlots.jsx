import { useMemo, useState } from 'react'
import { scaleLinear, scaleSqrt, line, area, curveMonotoneX } from 'd3'
import { formatDuration, formatHour } from '../../lib/listeningHistory'

const ACCENT = 'var(--route-accent)'
const GONE = '#FF7A9C'

/**
 * Artists placed on a day dial: angle is the hour they occupy, distance from
 * the centre is how tightly they sit there. A ranked list can only order them;
 * this shows that two artists share an hour while one owns it and the other is
 * played at any time.
 */
export function ArtistDayDial({ rows }) {
  const [hover, setHover] = useState(null)
  const SIZE = 460
  const R = 168
  const r = scaleLinear().domain([0, 1]).range([26, R])
  const size = scaleSqrt().domain([0, Math.max(...rows.map(d => d.plays), 1)]).range([3, 13])

  const pts = rows.map(d => {
    const a = (d.hour / 24) * Math.PI * 2 - Math.PI / 2
    return { ...d, cx: Math.cos(a) * r(d.focus), cy: Math.sin(a) * r(d.focus), rad: size(d.plays) }
  })
  const active = hover != null ? pts.find(p => p.artist === hover) : null

  return (
    <div className="listening-dial">
      <svg viewBox={`${-SIZE / 2} ${-SIZE / 2} ${SIZE} ${SIZE}`} role="img"
           aria-label="Top artists positioned by the hour they occupy and how focused they are">
        {[0.25, 0.5, 0.75, 1].map(f => (
          <circle key={f} r={r(f)} fill="none" stroke="var(--hairline)" strokeWidth="1" opacity="0.55" />
        ))}
        {[0, 3, 6, 9, 12, 15, 18, 21].map(h => {
          const a = (h / 24) * Math.PI * 2 - Math.PI / 2
          return (
            <g key={h}>
              <line x1={Math.cos(a) * 26} y1={Math.sin(a) * 26}
                    x2={Math.cos(a) * R} y2={Math.sin(a) * R}
                    stroke="var(--hairline)" strokeWidth="1" opacity="0.35" />
              <text x={Math.cos(a) * (R + 22)} y={Math.sin(a) * (R + 22)}
                    textAnchor="middle" dominantBaseline="middle" className="listening-dial-tick">
                {formatHour(h)}
              </text>
            </g>
          )
        })}

        {pts.map(p => (
          <g key={p.artist} onMouseEnter={() => setHover(p.artist)} onMouseLeave={() => setHover(null)}>
            <line x1={0} y1={0} x2={p.cx} y2={p.cy} stroke={ACCENT}
                  strokeWidth="1" opacity={hover === p.artist ? 0.5 : 0.13} />
            <circle cx={p.cx} cy={p.cy} r={p.rad} fill={ACCENT}
                    opacity={hover == null || hover === p.artist ? 0.85 : 0.25} />
          </g>
        ))}

        <text textAnchor="middle" y={-4} className="listening-dial-center">
          {active ? active.artist : 'your day'}
        </text>
        <text textAnchor="middle" y={16} className="listening-dial-sub">
          {active
            ? `${formatHour(Math.round(active.hour) % 24)} · ${(active.focus * 100).toFixed(0)}% focus`
            : 'centre = played anytime'}
        </text>
      </svg>
    </div>
  )
}

/**
 * Obsessions across time: when each burst happened and how intense it was.
 * A list flattens them into a ranking; on a timeline you can see that they
 * cluster, and which ones were never played again.
 */
export function ObsessionTimeline({ rows, range }) {
  const [hover, setHover] = useState(null)
  const W = 900, H = 300
  const PAD = { t: 18, r: 18, b: 34, l: 44 }

  const x = scaleLinear()
    .domain([range.from.getTime(), range.to.getTime()])
    .range([PAD.l, W - PAD.r])
  const y = scaleLinear()
    .domain([0, Math.max(...rows.map(d => d.peakPlays)) * 1.15])
    .range([H - PAD.b, PAD.t])
  const size = scaleSqrt().domain([0, Math.max(...rows.map(d => d.peakPlays))]).range([4, 26])

  const years = []
  for (let yr = range.from.getFullYear(); yr <= range.to.getFullYear(); yr += 1) {
    const t = new Date(yr, 0, 1).getTime()
    if (t >= range.from.getTime() && t <= range.to.getTime()) years.push({ yr, x: x(t) })
  }
  const active = hover ? rows.find(r => `${r.track}${r.artist}` === hover) : null

  return (
    <div className="listening-timeline">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Obsession bursts over time">
        {y.ticks(4).map(t => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)}
                  stroke="var(--hairline)" strokeWidth="1" opacity="0.4" />
            <text x={PAD.l - 8} y={y(t)} textAnchor="end" dominantBaseline="middle"
                  className="listening-plot-tick">{t}</text>
          </g>
        ))}
        {years.map(t => (
          <g key={t.yr}>
            <line x1={t.x} x2={t.x} y1={PAD.t} y2={H - PAD.b}
                  stroke="var(--hairline)" strokeWidth="1" opacity="0.4" />
            <text x={t.x} y={H - 12} textAnchor="middle" className="listening-plot-tick">{t.yr}</text>
          </g>
        ))}

        {rows.map(d => {
          const key = `${d.track}${d.artist}`
          return (
            <circle key={key} cx={x(d.windowStart.getTime())} cy={y(d.peakPlays)} r={size(d.peakPlays)}
                    fill={d.abandoned ? GONE : ACCENT}
                    opacity={hover == null || hover === key ? 0.62 : 0.18}
                    stroke={d.abandoned ? GONE : ACCENT} strokeWidth="1"
                    onMouseEnter={() => setHover(key)} onMouseLeave={() => setHover(null)} />
          )
        })}

        <text x={PAD.l - 8} y={PAD.t - 6} textAnchor="end" className="listening-plot-axis">plays / 14d</text>
      </svg>

      <p className="listening-plot-caption">
        {active
          ? <><b>{active.track}</b> — {active.artist} · {active.peakPlays}× in a fortnight from{' '}
              {active.windowStart.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
              {active.abandoned ? ', never played again' : ', still in rotation'}</>
          : <>Each circle is a track played hard inside one fortnight. Pink means it was never
              played again.</>}
      </p>
    </div>
  )
}

/**
 * Every session as a point: when it started against how long it ran. The
 * daily rhythm and the rare marathons both show up, and neither survives being
 * reduced to a median.
 */
export function SessionScatter({ points, median }) {
  const W = 900, H = 280
  const PAD = { t: 16, r: 16, b: 34, l: 52 }
  const x = scaleLinear().domain([0, 24]).range([PAD.l, W - PAD.r])
  const maxMin = Math.max(...points.map(p => p.ms)) / 60000
  // Sessions are heavily skewed: a log scale keeps the many short ones legible
  // instead of squashing them against the axis under a few long ones.
  const y = scaleLinear().domain([Math.log10(1), Math.log10(maxMin)]).range([H - PAD.b, PAD.t])
  const ly = v => y(Math.log10(Math.max(1, v)))

  return (
    <div className="listening-scatter">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label="Listening sessions by start hour and duration">
        {[1, 10, 60, 600].filter(v => v <= maxMin).map(v => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={ly(v)} y2={ly(v)}
                  stroke="var(--hairline)" strokeWidth="1" opacity="0.4" />
            <text x={PAD.l - 8} y={ly(v)} textAnchor="end" dominantBaseline="middle"
                  className="listening-plot-tick">{v < 60 ? `${v}m` : `${v / 60}h`}</text>
          </g>
        ))}
        {[0, 6, 12, 18, 24].map(h => (
          <g key={h}>
            <line x1={x(h)} x2={x(h)} y1={PAD.t} y2={H - PAD.b}
                  stroke="var(--hairline)" strokeWidth="1" opacity="0.4" />
            <text x={x(h)} y={H - 12} textAnchor="middle" className="listening-plot-tick">
              {formatHour(h % 24)}
            </text>
          </g>
        ))}
        <line x1={PAD.l} x2={W - PAD.r} y1={ly(median / 60000)} y2={ly(median / 60000)}
              stroke={ACCENT} strokeWidth="1" strokeDasharray="4 4" opacity="0.7" />

        {points.map((p, i) => (
          <circle key={i} cx={x(p.hour)} cy={ly(p.ms / 60000)} r={2.4}
                  fill={p.weekend ? '#5AC8FA' : ACCENT} opacity="0.34" />
        ))}
      </svg>
      <div className="listening-plot-key">
        <span><i style={{ background: ACCENT }} />weekday</span>
        <span><i style={{ background: '#5AC8FA' }} />weekend</span>
        <span><i className="dash" />median {formatDuration(median)}</span>
      </div>
    </div>
  )
}

/**
 * Lorenz curve of listening across artists. The diagonal is a listener who
 * spreads time evenly; the further the curve bows, the more a handful of
 * artists carry everything.
 */
export function ConcentrationCurve({ data }) {
  const W = 620, H = 300
  const PAD = { t: 16, r: 18, b: 34, l: 44 }
  const x = scaleLinear().domain([0, 1]).range([PAD.l, W - PAD.r])
  const y = scaleLinear().domain([0, 1]).range([H - PAD.b, PAD.t])

  // x and y are rebuilt each render from constant domains, so they are stable
  // in every way that matters here; listing them would defeat the memo.
  const path = useMemo(() => line().x(d => x(d.x)).y(d => y(d.y)).curve(curveMonotoneX)(
    [{ x: 0, y: 0 }, ...data.curve]), [data])   // eslint-disable-line react-hooks/exhaustive-deps
  const fill = useMemo(() => area().x(d => x(d.x)).y0(y(0)).y1(d => y(d.y)).curve(curveMonotoneX)(
    [{ x: 0, y: 0 }, ...data.curve]), [data])   // eslint-disable-line react-hooks/exhaustive-deps

  const halfX = data.artistsForHalf / data.artists
  return (
    <div className="listening-lorenz">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label="Share of listening time by share of artists">
        {[0.25, 0.5, 0.75, 1].map(t => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)}
                  stroke="var(--hairline)" strokeWidth="1" opacity="0.4" />
            <text x={PAD.l - 8} y={y(t)} textAnchor="end" dominantBaseline="middle"
                  className="listening-plot-tick">{t * 100}%</text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)}
              stroke="var(--text-low)" strokeWidth="1" strokeDasharray="4 4" opacity="0.5" />
        <path d={fill} fill={ACCENT} opacity="0.13" />
        <path d={path} fill="none" stroke={ACCENT} strokeWidth="2" />

        <line x1={x(halfX)} x2={x(halfX)} y1={y(0)} y2={y(0.5)}
              stroke={ACCENT} strokeWidth="1" opacity="0.55" />
        <circle cx={x(halfX)} cy={y(0.5)} r="4" fill={ACCENT} />
        <text x={x(halfX) + 8} y={y(0.5) - 8} className="listening-plot-note">
          {data.artistsForHalf} artists = half your hours
        </text>
        <text x={(PAD.l + W - PAD.r) / 2} y={H - 12} textAnchor="middle"
              className="listening-plot-tick">share of your artists →</text>
      </svg>
    </div>
  )
}

/** New artists per month: whether you were still opening up or settling in. */
export function DiscoveryPlot({ rows }) {
  const W = 900, H = 240
  const PAD = { t: 16, r: 18, b: 34, l: 44 }
  const x = scaleLinear().domain([0, Math.max(1, rows.length - 1)]).range([PAD.l, W - PAD.r])
  const y = scaleLinear().domain([0, Math.max(...rows.map(d => d.fresh), 1) * 1.1])
    .range([H - PAD.b, PAD.t])

  const fill = area().x((_, i) => x(i)).y0(y(0)).y1(d => y(d.fresh)).curve(curveMonotoneX)(rows)
  const stroke = line().x((_, i) => x(i)).y(d => y(d.fresh)).curve(curveMonotoneX)(rows)
  const ticks = rows.map((r, i) => ({ ...r, i })).filter(r => r.month.endsWith('-01'))

  return (
    <div className="listening-discovery">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="New artists discovered each month">
        {y.ticks(4).map(t => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)}
                  stroke="var(--hairline)" strokeWidth="1" opacity="0.4" />
            <text x={PAD.l - 8} y={y(t)} textAnchor="end" dominantBaseline="middle"
                  className="listening-plot-tick">{t}</text>
          </g>
        ))}
        {ticks.map(t => (
          <g key={t.month}>
            <line x1={x(t.i)} x2={x(t.i)} y1={PAD.t} y2={H - PAD.b}
                  stroke="var(--hairline)" strokeWidth="1" opacity="0.4" />
            <text x={x(t.i)} y={H - 12} textAnchor="middle" className="listening-plot-tick">
              {t.month.slice(0, 4)}
            </text>
          </g>
        ))}
        <path d={fill} fill={ACCENT} opacity="0.16" />
        <path d={stroke} fill="none" stroke={ACCENT} strokeWidth="2" />
        <text x={PAD.l - 8} y={PAD.t - 4} textAnchor="end" className="listening-plot-axis">new artists</text>
      </svg>
    </div>
  )
}
