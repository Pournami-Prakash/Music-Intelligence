import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import DemoBadge from '../components/DemoBadge'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp, EqualizerBars, OrbitSystem, SpinningRecord } from '../components/Observatory'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#3DDC97'

const MOCK = {
  artist: 'Drake',
  playlist_count: 142312,
  pct: 14.23,
  rank: 1,
  top_track: 'God’s Plan',
  track_playlists: 421043,
  co_artists: [
    { name: 'Kendrick Lamar', overlap_pct: 72.3 },
    { name: 'J. Cole', overlap_pct: 68.1 },
    { name: 'Future', overlap_pct: 64.7 },
    { name: 'Travis Scott', overlap_pct: 61.2 },
    { name: 'Lil Baby', overlap_pct: 58.9 },
  ],
}

const SUGGESTIONS = ['Drake', 'Taylor Swift', 'The Weeknd', 'Kendrick Lamar', 'Billie Eilish']

export default function ArtistUbiquity() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.artist) { setQuery(s.artist); search(s.artist) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const data = await getJson(`/api/artist-ubiquity/${encodeURIComponent(q)}`)
      setResult({
        ...MOCK,
        artist: data.artist,
        playlist_count: data.playlist_count,
        pct: parseFloat(data.pct.toFixed(2)),
        rank: data.rank ?? MOCK.rank,
        top_track: data.top_tracks?.[0]?.track_name ?? MOCK.top_track,
        track_playlists: data.top_tracks?.[0]?.count ?? MOCK.track_playlists,
        co_artists: data.co_artists?.length ? data.co_artists : MOCK.co_artists,
      })
    } catch (e) {
      setResult({ ...MOCK, artist: q, _demo: true, _error: errorMessage(e) })
    } finally {
      setLoading(false)
    }
  }

  const reachClass = result?.pct > 10 ? 'Top 1%' : result?.pct > 5 ? 'High orbit' : 'Niche signal'

  return (
    <div className="pv">
      <div className="pv-top">
        <div className="pv-brand"><b>Music Intelligence Atlas</b> · Artist reach</div>
        <div className="pv-pill">Playlist footprint</div>
      </div>

      <header className="pv-hero">
        <p className="pv-eyebrow">Artist Observatory</p>
        <h1>{result?.artist || 'Artist Ubiquity'}</h1>
        <p>Measure how widely an artist travels across playlist culture — and which artists orbit them.</p>
      </header>

      <form className="pv-search" onSubmit={e => { e.preventDefault(); search(query) }}>
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search an artist..." />
        <button disabled={!query.trim() || loading}>{loading ? 'Measuring…' : 'Measure reach'}</button>
      </form>

      <div className="pv-chips">
        <span>Try</span>
        {SUGGESTIONS.map(s => (
          <button key={s} onClick={() => { setQuery(s); search(s) }}>{s}</button>
        ))}
      </div>

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/vinyl-loading.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Reading playlist footprint…</p>
            </div>
          </div>
        )}

        {result && !loading && (
          <div key={result.artist} className="space-y-4">
            {result._demo && <DemoBadge detail={result._error} />}
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_400px] gap-4">
              <section className="pv-panel atlas-rise" style={{ '--i': 0 }}>
                <p className="pv-panel-label">Saturation record</p>
                <div className="grid grid-cols-1 lg:grid-cols-[210px_minmax(0,1fr)] gap-8 items-center">
                  <SpinningRecord label={result.artist} sub={result.top_track} accent={ACCENT} />
                  <div>
                    <p className="text-[76px] sm:text-[92px] leading-none font-extrabold tracking-[-0.04em]" style={{ color: ACCENT }}>
                      <CountUp value={result.pct} decimals={2} /><span className="text-3xl align-top">%</span>
                    </p>
                    <p className="text-2xl font-bold mt-2 text-[var(--text-hi)]">playlist saturation</p>
                    <p className="mt-3 text-[var(--text-mid)]">
                      <CountUp value={result.playlist_count} /> playlists · ranked #{result.rank} by visible footprint.
                    </p>
                    <div className="grid grid-cols-2 gap-3 mt-6">
                      <div className="pv-cell">
                        <small>Most visible track</small>
                        <strong>{result.top_track}</strong>
                        <span className="text-xs" style={{ color: ACCENT }}><CountUp value={result.track_playlists} /> playlists</span>
                      </div>
                      <div className="pv-cell">
                        <small>Reach class</small>
                        <strong>{reachClass}</strong>
                        <span className="text-xs text-[var(--text-low)]">playlist frequency</span>
                      </div>
                    </div>
                    <div className="mt-6"><EqualizerBars color={ACCENT} /></div>
                  </div>
                </div>
              </section>

              <section className="pv-panel atlas-rise" style={{ '--i': 1 }}>
                <p className="pv-panel-label">Orbiting artists</p>
                <OrbitSystem center={result.artist} neighbors={result.co_artists.slice(0, 5)} accent={ACCENT} />
                <p className="text-center text-[11px] mt-2 mb-4 text-[var(--text-low)]">
                  hover to pause · click an orbit to open compass
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <Link to="/artist-habitat" state={{ artist: result.artist }} className="pv-link">Open habitat</Link>
                  <Link
                    to="/overlap-arena"
                    state={{ a: result.artist, b: result.co_artists[0]?.name || 'Kendrick Lamar' }}
                    className="pv-link"
                  >
                    Compare overlap
                  </Link>
                </div>
              </section>
            </div>
          </div>
        )}

        {!result && !loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/radar.json" className="w-44 h-44 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Search an artist to open their playlist footprint dossier.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
