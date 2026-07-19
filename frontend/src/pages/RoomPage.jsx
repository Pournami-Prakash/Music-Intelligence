import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight } from 'lucide-react'
import { ROOMS } from '../data/rooms'
import { iconFor } from '../lib/icons'

export default function RoomPage({ roomId }) {
  const room = ROOMS[roomId]

  if (!room) {
    return (
      <div className="pv">
        <div className="pv-top"><div className="pv-brand"><b>Music Intelligence Atlas</b> · Unknown room</div><div className="pv-pill">404</div></div>
        <header className="pv-hero"><p className="pv-eyebrow">Missing room</p><h1>Room not found</h1><p>This atlas room is not registered.</p></header>
      </div>
    )
  }

  // The room's first tool is the recommended starting point; the rest become a
  // lean iconed menu. Presenting the tools *is* the room's job — so the page
  // leads with them instead of a decorative hero.
  const [featured, ...rest] = room.features
  const [fLabel, fTo, fDesc, fState, fIcon] = featured
  const FIcon = iconFor(fIcon)

  return (
    <div className="pv" style={{ '--accent': room.accent }}>
      <div className="pv-top">
        <div className="pv-brand"><b>{room.name}</b> · {room.eyebrow}</div>
        <div className="pv-pill">{room.code} room</div>
      </div>

      <header className="atlas-room-head atlas-rise" style={{ '--i': 0 }}>
        <p className="pv-eyebrow">Room {room.code} · {room.features.length} instruments</p>
        <h1>{room.name}</h1>
        <p className="atlas-room-lede">{room.description}</p>
        <div className="atlas-room-tags">
          {room.stats.map(s => <span key={s}>{s}</span>)}
        </div>
      </header>

      <section className="atlas-room-hub">
        <Link
          to={fTo}
          state={fState}
          className="atlas-room-featured atlas-rise group"
          style={{ '--i': 1 }}
        >
          <span className="atlas-room-featured-badge">Start here</span>
          <span className="atlas-room-featured-icon"><FIcon size={22} /></span>
          <h2>{fLabel}</h2>
          <p>{fDesc}</p>
          <span className="atlas-room-featured-cta">Enter experiment <ArrowRight size={15} /></span>
        </Link>

        <nav className="atlas-room-menu" aria-label={`${room.name} tools`}>
          {rest.map(([label, to, desc, state, icon], i) => {
            const Icon = iconFor(icon)
            return (
              <Link
                key={to}
                to={to}
                state={state}
                className="atlas-room-row atlas-rise group"
                style={{ '--i': i + 2 }}
              >
                <span className="atlas-room-row-icon"><Icon size={17} /></span>
                <span className="atlas-room-row-body">
                  <strong>{label}</strong>
                  <em>{desc}</em>
                </span>
                <ArrowUpRight size={15} className="atlas-room-row-arrow" />
              </Link>
            )
          })}
        </nav>
      </section>
    </div>
  )
}
