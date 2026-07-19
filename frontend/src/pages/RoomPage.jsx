import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight } from 'lucide-react'
import { ROOMS } from '../data/rooms'
import LottiePlayer from '../components/LottiePlayer'

const ROOM_LOTTIES = {
  'deep-map': '/assets/radar.json',
  'artist-observatory': '/assets/earth-connections.json',
  'song-world': '/assets/turntable.json',
  'vibe-dictionary': '/assets/letters.lottie',
  'taste-tunnel': '/assets/cloud-technology.lottie',
  'drop-archive': '/assets/cassette-tape.lottie',
}

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

      <section className="pv-room-stage">
        <div className="pv-room-stage-copy">
          <p className="pv-eyebrow">Room {room.code} / Begin here</p>
          <h1>{room.name}</h1>
          <p>{room.description}</p>
          <div className="pv-room-signal-line">
            {room.stats.map((stat, i) => <span key={stat}>0{i + 1} {stat}</span>)}
          </div>
          <div className="pv-room-primary">
            <small>Recommended first experiment</small>
            <strong>{room.primary[0]}</strong>
            <Link
              to={room.primary[1]}
              state={room.primary[2]}
              className="inline-flex items-center justify-center gap-2 px-5 py-3 text-sm font-semibold"
              style={{ background: room.accent, color: '#04140D' }}
            >
              Enter experiment <ArrowRight size={15} />
            </Link>
          </div>
        </div>

        <div className="pv-room-lottie">
          <LottiePlayer src={ROOM_LOTTIES[roomId]} className="w-full h-full" />
          <span>{room.code} / instrument active</span>
        </div>
      </section>

      <section className="pv-feature-path max-w-6xl">
        <div className="pv-section-intro">
          <p>Continue through the room</p>
          <h2>Follow the next interesting signal.</h2>
        </div>
          <div className="pv-feature-list">
            {room.features.map(([label, to, desc, state], i) => (
              <Link
                key={to}
                to={to}
                state={state}
                className="pv-feature-entry group"
              >
                <span>{String(i + 1).padStart(2, '0')}</span>
                <div className="min-w-0">
                  <h3>{label}</h3>
                  <p>{desc}</p>
                </div>
                <ArrowUpRight size={15} style={{ color: room.accent }} className="opacity-60 group-hover:opacity-100" />
              </Link>
            ))}
          </div>
      </section>
    </div>
  )
}
