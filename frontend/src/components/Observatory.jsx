import { Link } from 'react-router-dom'
import { useCountUp } from '../hooks/useCountUp'

/**
 * Motion primitives for the Atlas "product" language.
 *
 * These are deliberately generic so other pages can adopt the same motion
 * vocabulary as the redesign rolls out:
 *   CountUp        — a number that animates up on mount / change
 *   EqualizerBars  — a bar field that pulses like a playing track
 *   SpinningRecord — an artist rendered as a rotating vinyl record
 *   OrbitSystem    — neighbours revolving around a subject by strength
 *
 * All continuous motion is CSS-driven (see index.css) and disabled under
 * prefers-reduced-motion.
 */

export function CountUp({ value, decimals = 0, suffix = '', className }) {
  const n = useCountUp(value, { duration: 1200, decimals })
  return (
    <span className={className}>
      {n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
      {suffix}
    </span>
  )
}

export function EqualizerBars({ color = '#34D399', bars = 44 }) {
  return (
    <div className="atlas-eq" aria-hidden="true">
      {Array.from({ length: bars }).map((_, i) => (
        <i
          key={i}
          className="atlas-eq-bar"
          style={{
            background: color,
            height: `${28 + ((i * 37) % 68)}%`,
            animationDelay: `${(i % 9) * 80}ms`,
          }}
        />
      ))}
    </div>
  )
}

export function SpinningRecord({ label, sub, accent = '#34D399' }) {
  const initial = (label || '?').trim().charAt(0).toUpperCase() || '?'
  return (
    <div className="atlas-record" style={{ '--rec': accent }}>
      <div className="atlas-record-plate">
        <div className="atlas-record-disc atlas-vinyl">
          <span className="atlas-record-center">{initial}</span>
        </div>
        <span className="atlas-record-arm" aria-hidden="true" />
      </div>
      <div className="atlas-record-meta">
        <span>artist record</span>
        <strong>{label}</strong>
        {sub && <small>{sub}</small>}
      </div>
    </div>
  )
}

export function OrbitSystem({ center, neighbors = [], accent = '#34D399' }) {
  const n = neighbors.length || 1
  return (
    <div
      className="atlas-orbit"
      role="img"
      aria-label={`Orbit chart: ${neighbors.length} artists placed around ${center} by playlist overlap strength`}
    >
      <span className="atlas-orbit-ring" style={{ inset: '7%' }} />
      <span className="atlas-orbit-ring" style={{ inset: '21%' }} />
      <span className="atlas-orbit-ring" style={{ inset: '35%' }} />
      <span className="atlas-orbit-cross atlas-orbit-cross-v" />
      <span className="atlas-orbit-cross atlas-orbit-cross-h" />

      <div className="atlas-orbit-rotor">
        {neighbors.map((a, i) => {
          const strength = Math.min(1, Math.max(0, (a.overlap_pct ?? 0) / 100))
          const angle = (i / n) * 360
          const radius = 46 - strength * 17     // closer when stronger (cqmin units)
          const size = 30 + strength * 26
          return (
            <Link
              key={a.name}
              to="/compass"
              state={{ artist: a.name }}
              title={`Open ${a.name} in Compass · ${Math.round(a.overlap_pct)}% overlap`}
              className="atlas-orbit-node"
              style={{ '--a': `${angle}deg`, '--r': radius }}
            >
              <span className="atlas-orbit-face">
                <span
                  className="atlas-orbit-disc"
                  style={{ width: `${size}px`, height: `${size}px`, '--rec': accent }}
                >
                  {Math.round(a.overlap_pct)}
                </span>
                <span className="atlas-orbit-name">{a.name}</span>
              </span>
            </Link>
          )
        })}
      </div>

      <div className="atlas-orbit-core" style={{ '--rec': accent }}>
        <span className="atlas-orbit-core-pulse" />
        <strong>{center}</strong>
        <small>subject</small>
      </div>
    </div>
  )
}
