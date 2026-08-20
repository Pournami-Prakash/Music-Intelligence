import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpRight, Search } from 'lucide-react'
import { animate, inView, scroll, stagger } from 'motion'
import { ROOM_ORDER, ROOMS } from '../data/rooms'
import { CountUp } from '../components/Observatory'
import CorpusSignal from '../components/CorpusSignal'
import ScrollAct from '../components/home/ScrollAct'
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

const SEARCH_STARTERS = [
  { label: 'Taylor Swift', query: 'Taylor Swift' },
  { label: 'Radiohead', query: 'Radiohead' },
  { label: 'Drake → Radiohead', to: '/six-degrees', state: { from: 'Drake', to: 'Radiohead' } },
]

// Hero headline, split into cinematically masked lines.
const TITLE_LINES = [
  [{ t: 'Hear what' }],
  [{ t: 'a million' }],
  [{ t: 'playlists', accent: true }, { t: ' reveal.' }],
]

export default function Home() {
  const [stats, setStats] = useState(DEFAULT_STATS)
  const [query, setQuery] = useState('')
  const [reduceMotion] = useState(() => typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const pageRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetch(apiUrl('/api/stats')).then(r => r.json()).then(setStats).catch(() => {})
  }, [])

  useEffect(() => {
    const page = pageRef.current
    if (!page) return undefined
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduceMotion) {
      page.dataset.motionReady = 'reduced'
      return undefined
    }

    page.dataset.motionReady = 'true'
    const controls = []
    const cleanups = []
    const push = (c) => { if (c) controls.push(c) }

    const q = (sel) => page.querySelector(sel)
    const qa = (sel) => Array.from(page.querySelectorAll(sel))

    // 0 ─ Cinematic curtain: letterbox bars part on first visit of the session.
    const firstOpen = !sessionStorage.getItem('atlas-opened')
    const bars = Array.from(document.querySelectorAll('.pv-cinema-bar'))
    if (firstOpen && bars.length) {
      sessionStorage.setItem('atlas-opened', '1')
      push(animate(
        bars,
        { transform: ['scaleY(1)', 'scaleY(0)'] },
        { duration: 0.92, delay: 0.05, ease: [0.85, 0, 0.15, 1] },
      ))
    } else {
      bars.forEach(b => { b.style.transform = 'scaleY(0)' })
    }
    const introLag = firstOpen ? 0.5 : 0.05

    // 1 ─ Hero title: each line rises out from behind its mask (film-title reveal).
    const lines = qa('.pv-reveal-line > span')
    push(animate(
      lines,
      { transform: ['translateY(112%)', 'translateY(0%)'] },
      { duration: 0.92, delay: stagger(0.085, { startDelay: introLag }), ease: [0.16, 1, 0.3, 1] },
    ))

    // 2 ─ Supporting copy fades up in sequence.
    const intro = qa('[data-motion-intro]')
    push(animate(
      intro,
      { opacity: [0, 1], transform: ['translateY(20px)', 'translateY(0px)'] },
      { duration: 0.8, delay: stagger(0.08, { startDelay: introLag + 0.28 }), ease: [0.22, 1, 0.36, 1] },
    ))

    // 3 ─ The signal instrument settles with a slow push-in (Ken Burns).
    const visual = q('.pv-home-lottie')
    push(animate(
      visual,
      { opacity: [0, 1], transform: ['scale(1.08) translateX(26px)', 'scale(1) translateX(0px)'] },
      { duration: 1.25, delay: introLag + 0.15, ease: [0.16, 1, 0.3, 1] },
    ))

    // 4 ─ Calibration sweep loops across the instrument.
    const sweep = q('.pv-signal-sweep')
    push(animate(
      sweep,
      { transform: ['translateX(-115%)', 'translateX(115%)'] },
      { duration: 3.4, delay: introLag + 1.1, repeat: Infinity, repeatDelay: 2.8, ease: 'linear' },
    ))

    // 5 ─ Scroll-driven reveals: sections resolve as they enter the frame.
    const revealables = qa('[data-motion-reveal]')
    revealables.forEach((el) => {
      el.style.opacity = '0'
      el.style.transform = 'translateY(34px)'
      const stop = inView(el, () => {
        const rows = el.querySelectorAll('.pv-room-entry')
        if (rows.length) {
          animate(el, { opacity: [0, 1] }, { duration: 0.4 })
          el.style.transform = 'none'
          animate(
            rows,
            { opacity: [0, 1], transform: ['translateY(40px)', 'translateY(0px)'] },
            { duration: 0.7, delay: stagger(0.07), ease: [0.16, 1, 0.3, 1] },
          )
        } else {
          animate(
            el,
            { opacity: [0, 1], transform: ['translateY(34px)', 'translateY(0px)'] },
            { duration: 0.72, ease: [0.16, 1, 0.3, 1] },
          )
        }
        return () => {}
      }, { amount: 0.25, margin: '0px 0px -12% 0px' })
      cleanups.push(stop)
    })

    // 6 ─ Parallax: the instrument and ambient wash drift against the scroll.
    if (visual) {
      cleanups.push(scroll(
        (progress) => {
          visual.style.setProperty('--parallax', `${(progress - 0.5) * -66}px`)
        },
        { target: page, offset: ['start start', 'end start'] },
      ))
    }
    const ambient = document.querySelector('.pv-cinema-wash')
    if (ambient) {
      cleanups.push(scroll(
        (progress) => {
          ambient.style.transform = `translate3d(0, ${progress * 120}px, 0) scale(${1 + progress * 0.12})`
        },
      ))
    }

    return () => {
      controls.forEach(control => control?.stop?.())
      cleanups.forEach(stop => stop?.())
    }
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
    <div className="pv pv-home" ref={pageRef}>
      {/* Cinematic framing — portaled to <body> so fixed positioning tracks the
          viewport (the route container keeps an inline transform). Decorative only. */}
      {createPortal(
        <div className="pv-cinema" aria-hidden="true">
          <div className="pv-cinema-wash" />
          <div className="pv-cinema-vignette" />
          <div className="pv-cinema-bar is-top" />
          <div className="pv-cinema-bar is-bottom" />
        </div>,
        document.body,
      )}

      {/* Cinematic hero backdrop — a living galaxy of playlists (z-index:-1).
          Autoplays muted/looping; reduced-motion users get the poster still.
          A left/bottom scrim keeps the headline and search legible. */}
      <div className="pv-ribbon-stage" aria-hidden="true">
        <video
          className="pv-hero-video"
          poster="/media/hero-network-poster.jpg"
          autoPlay={!reduceMotion}
          muted
          loop
          playsInline
          preload="metadata"
        >
          <source src="/media/hero-network.mp4" type="video/mp4" />
        </video>
        <div className="pv-hero-scrim" />
      </div>

      <div className="pv-top">
        <div className="pv-brand"><b>Music Intelligence Atlas</b> · Playlist culture</div>
        <div className="pv-pill">Active archive</div>
      </div>

      <section className="pv-home-stage">
        <div className="pv-home-copy">
          <p className="pv-eyebrow" data-motion-intro>Playlist intelligence / 01</p>
          <h1 className="pv-home-title">
            {TITLE_LINES.map((line, i) => (
              <span className="pv-reveal-line" key={i}>
                <span>
                  {line.map((part, j) => (
                    part.accent
                      ? <em className="pv-accent" key={j}>{part.t}</em>
                      : <span key={j}>{part.t}</span>
                  ))}
                </span>
              </span>
            ))}
          </h1>
          <p className="pv-home-deck" data-motion-intro>A cultural atlas built from the way people group music—not what a genre chart says, but where songs and artists actually live.</p>

          <form className="pv-search" onSubmit={openDossier} data-motion-intro>
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
          <div className="pv-search-starters" data-motion-intro>
            <span>Try a signal</span>
            {SEARCH_STARTERS.map(item => (
              <button
                key={item.label}
                type="button"
                onClick={() => item.to ? navigate(item.to, { state: item.state }) : setQuery(item.query)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="pv-home-lottie">
          <div className="pv-signal-sweep" aria-hidden="true" />
          <CorpusSignal />
        </div>
      </section>

      <div className="max-w-6xl mt-10">
        <div className="pv-provenance-rail" data-motion-reveal>
          {[
            [<CountUp key="p" value={stats.playlists} />, 'playlists'],
            [<CountUp key="t" value={stats.tracks / 1_000_000} decimals={2} suffix="M" />, 'tracks'],
            [<CountUp key="c" value={stats.playlist_track_rows / 1_000_000} suffix="M" />, 'co-occurrences'],
            [<CountUp key="e" value={stats.editorial_playlists} />, 'editorial lists'],
          ].map(([value, label], i) => (
            <div key={label} className="pv-provenance-item" style={{ '--i': i }}>
              <b>{value}</b>
              <small>{label}</small>
            </div>
          ))}
        </div>

      </div>

      <ScrollAct reduceMotion={reduceMotion} />

      <div className="max-w-6xl">
        <div className="pv-section-intro" data-motion-reveal>
          <p>Six ways into the archive</p>
          <h2>Choose the question, not the chart.</h2>
        </div>
        <div className="pv-room-index" data-motion-reveal>
          {ROOM_ORDER.map((id, index) => {
            const room = ROOMS[id]
            return (
              <Link key={id} to={`/${id}`} className="pv-room-entry" style={{ '--rc': room.accent, '--i': index }}>
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

        <h2 className="pv-panel-label mt-16 mb-4" data-motion-reveal>Or jump straight into a known signal</h2>
        <div className="pv-fast-entries" data-motion-reveal>
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
