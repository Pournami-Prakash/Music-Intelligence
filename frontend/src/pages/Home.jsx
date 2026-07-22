import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpRight, Search } from 'lucide-react'
import { ROOM_ORDER, ROOMS } from '../data/rooms'
import { CountUp } from '../components/Observatory'
import LottiePlayer from '../components/LottiePlayer'
import { apiUrl } from '../lib/api'

const DEFAULT_STATS = {
  playlists: 1_000_000,
  tracks: 3_620_989,
  playlist_track_rows: 66_346_428,
  editorial_playlists: 9_053,
}

const ROOM_META = {
  'deep-map': ['Mood territories', 'genre drift', 'lineage'],
  'artist-observatory': ['reach radar', 'habitat scan', 'overlap field'],
  'song-world': ['track passport', 'context drift', 'gift arc'],
  'vibe-dictionary': ['title corpus', 'phrase evidence', 'naming rituals'],
  'taste-tunnel': ['pathfinder', 'bridge tracks', 'group blend'],
  'drop-archive': ['editorial removals', 'time capsule', 'forgotten hits'],
}

const FAST_ENTRY = [
  ['Drake footprint', '/artist-ubiquity', { artist: 'Drake' }, '#3DDC97'],
  ['Mr. Brightside passport', '/song-passport', { track: 'Mr. Brightside' }, '#5AC8FA'],
  ['Drake → Radiohead', '/six-degrees', { from: 'Drake', to: 'Radiohead' }, '#B08CF8'],
]

export default function Home() {
  const [stats, setStats] = useState(DEFAULT_STATS)
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    fetch(apiUrl('/api/stats')).then(r => r.json()).then(setStats).catch(() => {})
  }, [])

  const openDossier = (event) => {
    event.preventDefault()
    const q = query.trim()
    if (!q) return
    const roomMatch = ROOM_ORDER.find(id => ROOMS[id].name.toLowerCase().includes(q.toLowerCase()))
    if (roomMatch) { navigate(`/${roomMatch}`); return }
    navigate('/artist-ubiquity', { state: { artist: q } })
  }

  return (
    <div className="pv">
      <div className="pv-top">
        <div className="pv-brand"><b>Music Intelligence Atlas</b> · Playlist culture</div>
        <div className="pv-pill">Active archive</div>
      </div>

      <section className="pv-home-stage">
        <div className="pv-home-copy">
          <p className="pv-eyebrow">Playlist intelligence / 01</p>
          <h1>Hear what<br />a million<br /><span>playlists</span> reveal.</h1>
          <p className="pv-home-deck">A cultural atlas built from the way people group music—not what a genre chart says, but where songs and artists actually live.</p>

          <form className="pv-search" onSubmit={openDossier}>
            <div className="pv-search-field">
              <Search size={16} className="text-[var(--text-low)] shrink-0" />
              <input
                aria-label="Atlas search"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Artist, song, or room…"
              />
            </div>
            <button type="submit" disabled={!query.trim()}>Enter Atlas</button>
          </form>
        </div>

        <div className="pv-home-lottie">
          <LottiePlayer src="/assets/earth-connections.json" className="w-full h-full" />
          <div className="pv-stage-caption"><span>Live corpus</span><b>66M relationships</b></div>
        </div>
      </section>

      <div className="max-w-6xl mt-10">
        <div className="pv-provenance-rail">
          {[
            [<CountUp key="p" value={stats.playlists} />, 'playlists'],
            [<CountUp key="t" value={stats.tracks / 1_000_000} decimals={2} suffix="M" />, 'tracks'],
            [<CountUp key="c" value={stats.playlist_track_rows / 1_000_000} suffix="M" />, 'co-occurrences'],
            [<CountUp key="e" value={stats.editorial_playlists} />, 'editorial lists'],
          ].map(([value, label], i) => (
            <div key={label} className="pv-provenance-item atlas-rise" style={{ '--i': i }}>
              <b>{value}</b>
              <small>{label}</small>
            </div>
          ))}
        </div>

        <div className="pv-section-intro">
          <p>Six ways into the archive</p>
          <h2>Choose the question, not the chart.</h2>
        </div>
        <div className="pv-room-index">
          {ROOM_ORDER.map((id, index) => {
            const room = ROOMS[id]
            return (
              <Link key={id} to={`/${id}`} className="pv-room-entry atlas-rise" style={{ '--rc': room.accent, '--i': index }}>
                <span className="pv-room-number">0{index + 1}</span>
                <ArrowUpRight size={16} className="pv-card-arrow" />
                <div>
                  <span className="pv-card-eyebrow">{room.eyebrow}</span>
                  <h3>{room.name}</h3>
                </div>
                <p>{room.description}</p>
                <div className="pv-room-signals">
                  {(ROOM_META[id] || room.stats).map(item => <span key={item}>{item}</span>)}
                </div>
              </Link>
            )
          })}
        </div>

        <h2 className="pv-panel-label mt-16 mb-4">Or jump straight into a known signal</h2>
        <div className="pv-fast-entries">
          {FAST_ENTRY.map(([label, to, state, accent]) => (
            <Link key={label} to={to} state={state} className="pv-fast-entry" style={{ '--rc': accent }}>
              <ArrowUpRight size={15} className="pv-card-arrow" style={{ top: 18, right: 18 }} />
              <span className="text-sm font-semibold" style={{ color: accent }}>{label}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
