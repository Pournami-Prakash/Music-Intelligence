import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight } from 'lucide-react'
import { ROOMS } from '../data/rooms'

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

  return (
    <div className="pv" style={{ '--accent': room.accent }}>
      <div className="pv-top">
        <div className="pv-brand"><b>{room.name}</b> · {room.eyebrow}</div>
        <div className="pv-pill">{room.code} room</div>
      </div>

      <header className="pv-hero">
        <p className="pv-eyebrow">Room briefing</p>
        <h1>{room.name}</h1>
        <p>{room.description}</p>
      </header>

      <div className="max-w-6xl space-y-4">
        <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
          <section className="pv-panel atlas-rise" style={{ '--i': 0 }}>
            <p className="pv-panel-label">Recommended entry</p>
            <p className="text-xl font-bold text-[var(--text-hi)]">{room.primary[0]}</p>
            <p className="text-[var(--text-mid)] text-sm mt-1">Start here in {room.name}.</p>
            <Link
              to={room.primary[1]}
              state={room.primary[2]}
              className="mt-5 inline-flex items-center justify-center gap-2 w-full rounded-full px-5 py-2.5 text-sm font-semibold"
              style={{ background: room.accent, color: '#04140D' }}
            >
              Open feature <ArrowRight size={15} />
            </Link>
          </section>

          <section className="pv-panel atlas-rise" style={{ '--i': 1 }}>
            <p className="pv-panel-label">Room signals</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {room.stats.map((stat, i) => (
                <div key={stat} className="pv-cell">
                  <small>{String(i + 1).padStart(2, '0')} / {room.code}</small>
                  <strong className="text-base">{stat}</strong>
                </div>
              ))}
            </div>
            <p className="text-[var(--text-mid)] text-sm leading-relaxed mt-5">
              Use this room as a workflow: start with the recommended feature, then move through the records below when a result suggests the next question.
            </p>
          </section>
        </div>

        <section className="pv-panel atlas-rise" style={{ '--i': 2 }}>
          <p className="pv-panel-label">Feature workflow</p>
          <div className="space-y-px">
            {room.features.map(([label, to, desc, state], i) => (
              <Link
                key={to}
                to={to}
                state={state}
                className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-4 items-center py-3 px-2 rounded-lg border-b border-[var(--hairline)] last:border-0 hover:bg-white/[0.04] group"
              >
                <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                <div className="min-w-0">
                  <p className="text-[var(--text-hi)] text-sm font-medium">{label}</p>
                  <p className="text-[var(--text-low)] text-xs">{desc}</p>
                </div>
                <ArrowUpRight size={15} style={{ color: room.accent }} className="opacity-60 group-hover:opacity-100" />
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
