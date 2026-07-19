import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp, EqualizerBars, OrbitSystem, SpinningRecord } from '../components/Observatory'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#3DDC97'

const SUGGESTIONS = ['Drake', 'Taylor Swift', 'The Weeknd', 'Kendrick Lamar', 'Billie Eilish']

export default function ArtistUbiquity() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.artist) { setQuery(s.artist); search(s.artist) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await getJson(`/api/artist-ubiquity/${encodeURIComponent(q)}`)
      const firstTrack = data.top_tracks?.[0]
      setResult({ ...data,
        pct: Number(data.pct || 0),
        top_track: typeof firstTrack === 'string' ? firstTrack : firstTrack?.track_name,
        track_playlists: typeof firstTrack === 'object' ? firstTrack?.count : null,
        co_artists: data.co_artists || [],
      })
    } catch (e) {
      setError(errorMessage(e))
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
              <p className="mt-2 text-[var(--text-mid)]" role="status">Reading the full artist index. A cold demo can take up to a minute…</p>
            </div>
          </div>
        )}

        {error && !loading && (
          <ErrorSignal detail={error} onRetry={() => search(query)}>
            We couldn’t open this artist’s playlist footprint.
          </ErrorSignal>
        )}

        {result && !loading && !error && (
          <div key={result.artist} className="space-y-4">
            {result.detail_level === 'rank_only' && (
              <p className="atlas-coverage-note" role="status">
                Full-dataset rank and reach. Track and co-artist detail is currently available for the 10,000 most-playlisted artists.
              </p>
            )}
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_400px] gap-4">
              <section className="pv-panel atlas-rise" style={{ '--i': 0 }}>
                <p className="pv-panel-label">Saturation record</p>
                <div className="grid grid-cols-1 lg:grid-cols-[210px_minmax(0,1fr)] gap-8 items-center">
                  <SpinningRecord label={result.artist} sub={result.top_track || 'Full dataset rank'} accent={ACCENT} />
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
                        <strong>{result.top_track || 'Detail not cached'}</strong>
                        <span className="text-xs" style={{ color: ACCENT }}>{result.track_playlists != null ? <><CountUp value={result.track_playlists} /> playlists</> : 'Top-10K detail layer'}</span>
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
                {result.co_artists.length > 0 ? (
                  <>
                    <OrbitSystem center={result.artist} neighbors={result.co_artists.slice(0, 5)} accent={ACCENT} />
                    <p className="text-center text-[11px] mt-2 mb-4 text-[var(--text-low)]">hover to pause · click an orbit to open compass</p>
                  </>
                ) : (
                  <p className="text-[var(--text-mid)] text-sm py-12 text-center">Orbit detail is not cached for this long-tail artist. Their rank and reach above still use the full dataset.</p>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <Link to="/artist-habitat" state={{ artist: result.artist }} className="pv-link">Open habitat</Link>
                  <Link
                    to="/overlap-arena"
                    state={{ a: result.artist, b: result.co_artists[0]?.name || '' }}
                    className="pv-link"
                  >
                    Compare overlap
                  </Link>
                </div>
              </section>
            </div>
          </div>
        )}

        {!result && !loading && !error && (
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
