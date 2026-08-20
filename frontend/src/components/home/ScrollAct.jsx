import { useEffect, useRef, useState } from 'react'
import { scroll } from 'motion'
import { Link } from 'react-router-dom'

// The argument the whole atlas rests on, shown rather than asserted: one song
// filed by real people into contexts that contradict each other. The track is
// picked from the shipped snapshot at runtime, so it stays true if the data is
// rebuilt instead of freezing a claim into markup.
const CONTEXT_COLOR = {
  happy: '#F5C451', chill: '#22D3EE', sad: '#5AC8FA', heartbreak: '#B08CF8',
  gym: '#3DDC97', party: '#FB923C', study: '#B08CF8', sleep: '#94A3B8',
  angry: '#FF7A9C', anxious: '#FB923C', lonely: '#94A3B8',
}

function pickTrack(data) {
  const seen = new Map()
  Object.entries(data).forEach(([mood, blob]) => {
    (blob.tracks || []).forEach(t => {
      const key = `${t.title} ${t.artist}`
      if (!seen.has(key)) seen.set(key, { title: t.title, artist: t.artist, contexts: [] })
      seen.get(key).contexts.push({ mood, count: t.mood_appearances })
    })
  })
  // Most contexts wins, appearances break ties. A song in five contradictory
  // rooms makes the point that a song in two does not.
  const best = [...seen.values()]
    .sort((a, b) => b.contexts.length - a.contexts.length
      || b.contexts.reduce((s, c) => s + c.count, 0) - a.contexts.reduce((s, c) => s + c.count, 0))[0]
  if (!best || best.contexts.length < 3) return null
  best.contexts.sort((a, b) => b.count - a.count)
  return best
}

export default function ScrollAct({ reduceMotion }) {
  const [track, setTrack] = useState(null)
  const [step, setStep] = useState(0)
  const sectionRef = useRef(null)
  const stepRef = useRef(0)

  useEffect(() => {
    let live = true
    fetch('/data/mood-contradiction.json')
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (live && d) setTrack(pickTrack(d)) })
      .catch(() => {})
    return () => { live = false }
  }, [])

  useEffect(() => {
    const el = sectionRef.current
    if (!el || !track || reduceMotion) return undefined
    const n = track.contexts.length
    return scroll(
      progress => {
        // A continuous variable drives the rail, while discrete state changes
        // only at a boundary, so React re-renders a handful of times across the
        // whole scroll rather than on every frame.
        el.style.setProperty('--act-progress', progress.toFixed(4))
        const next = Math.min(n - 1, Math.max(0, Math.floor(progress * n * 0.999)))
        if (next !== stepRef.current) { stepRef.current = next; setStep(next) }
      },
      { target: el, offset: ['start start', 'end end'] },
    )
  }, [track, reduceMotion])

  if (!track) return null

  const active = track.contexts[step]
  const accent = CONTEXT_COLOR[active.mood] || 'var(--accent)'

  // Reduced motion gets the same evidence without the pinning.
  if (reduceMotion) {
    return (
      <section className="home-act home-act-static">
        <p className="home-act-kicker">One song, {track.contexts.length} contexts</p>
        <h2 className="home-act-title">{track.title}</h2>
        <p className="home-act-artist">{track.artist}</p>
        <ul className="home-act-list">
          {track.contexts.map(c => (
            <li key={c.mood} style={{ '--c': CONTEXT_COLOR[c.mood] || 'var(--accent)' }}>
              <b>{c.mood}</b><span>{c.count} playlists</span>
            </li>
          ))}
        </ul>
        <Link to="/guilty-pleasure" className="home-act-cta">See the whole ledger</Link>
      </section>
    )
  }

  return (
    <section
      ref={sectionRef}
      className="home-act"
      style={{ '--act-accent': accent, height: `${track.contexts.length * 90}vh` }}
    >
      <div className="home-act-pin">
        <p className="home-act-kicker">
          One song · {track.contexts.length} contradictory rooms
        </p>

        <h2 className="home-act-title">{track.title}</h2>
        <p className="home-act-artist">{track.artist}</p>

        <div className="home-act-swap" aria-live="polite">
          <span key={active.mood} className="home-act-context">
            filed under {active.mood}
          </span>
          <b key={`${active.mood}-n`} className="home-act-count">
            {active.count} <small>playlists</small>
          </b>
        </div>

        <div className="home-act-rail" aria-hidden="true">
          {track.contexts.map((c, i) => (
            <span key={c.mood}
                  className={i === step ? 'is-active' : undefined}
                  style={{ '--c': CONTEXT_COLOR[c.mood] || 'var(--accent)' }} />
          ))}
        </div>

        <p className="home-act-thesis">
          Same recording, different rooms. A genre chart cannot see this, because
          it is not a fact about the music. It is a fact about how people use it.
        </p>
        <Link to="/guilty-pleasure" className="home-act-cta">See the whole ledger</Link>
      </div>
    </section>
  )
}
