import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'

function systemString(code = 'MIA', label = 'atlas signal') {
  return `ROOM_${String(code).toUpperCase()} // ${String(label).replace(/\s+/g, '_').toUpperCase()}`
}

export function DossierPage({ accent = '#1ED760', children, className = '' }) {
  return (
    <div className={`dossier-page ${className}`} style={{ '--accent': accent }}>
      {children}
      <div className="dossier-ambient-strip" aria-hidden="true">
        <span>ARCHIVE: 1M PLAYLISTS</span>
        <span>TRACKS: 3.62M</span>
        <span>CO-OCCURRENCE ROWS: 66M</span>
      </div>
    </div>
  )
}

export function DossierTopbar({ label = 'Music Intelligence Atlas', meta = 'Playlist culture archive', right }) {
  return (
    <div className="dossier-topbar">
      <div>
        <strong>{label}</strong>
        <span>{meta}</span>
      </div>
      <div>{right}</div>
    </div>
  )
}

export function DossierHero({ eyebrow, title, subtitle, code }) {
  return (
    <header className="dossier-hero">
      <div>
        <p>{systemString(code, eyebrow)}</p>
        <h1>{title}</h1>
        {subtitle && <span>{subtitle}</span>}
      </div>
      {code && <em>{code}</em>}
    </header>
  )
}

export function DossierPanel({ label, action, children, className = '' }) {
  return (
    <section className={`dossier-panel ${className}`}>
      {(label || action) && (
        <div className="dossier-panel-head">
          {label && <p>{label}</p>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function DossierStamp({ children, tone }) {
  return (
    <span className="dossier-stamp" style={tone ? { '--stamp': tone } : undefined}>
      {children}
    </span>
  )
}

export function DossierArtifact({ title, subtitle, label, accent = '#1ED760', compact = false }) {
  return (
    <div className={`dossier-artifact ${compact ? 'is-compact' : ''}`} style={{ '--artifact': accent }}>
      <div className="dossier-artifact-sleeve">
        <span>{label || 'artifact'}</span>
        <strong>{title}</strong>
        {subtitle && <small>{subtitle}</small>}
      </div>
      <Waveform color={accent} />
    </div>
  )
}

export function Waveform({ color = '#1ED760', bars = 24 }) {
  return (
    <div className="dossier-waveform" style={{ '--wave': color }} aria-hidden="true">
      {Array.from({ length: bars }).map((_, i) => (
        <i
          key={i}
          style={{ height: `${22 + ((i * 17) % 54)}%`, opacity: 0.42 + ((i % 5) * 0.1) }}
        />
      ))}
    </div>
  )
}

export function MetricRow({ label, value, color = '#1ED760' }) {
  return (
    <div className="dossier-metric-row">
      <span>{label}</span>
      <div><i style={{ width: `${Math.min(100, Number(value) || 0)}%`, background: color }} /></div>
      <strong style={{ color }}>{value}%</strong>
    </div>
  )
}

export function RoomTile({ room, index, to, children }) {
  return (
    <Link className="dossier-room-tile" to={to} style={{ '--accent': room.accent }}>
      <div className="dossier-room-index">record_{String(index + 1).padStart(2, '0')}</div>
      <div className="dossier-room-arrow"><ArrowUpRight size={15} /></div>
      <h2>{room.name}</h2>
      <p>{room.description}</p>
      {children}
    </Link>
  )
}
