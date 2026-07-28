import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#B08CF8'
const EXAMPLES = [
  { a: 'Taylor Swift', b: 'Kendrick Lamar' },
  { a: 'Radiohead', b: 'Drake' },
  { a: 'ABBA', b: 'Tyler, the Creator' },
]

export default function SongCollision() {
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.a && s?.b) { setA(s.a); setB(s.b); search(s.a, s.b) }
  }, [location.state])

  const search = async (av, bv) => {
    if (!av?.trim() || !bv?.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const d = await getJson(`/api/collision?a=${encodeURIComponent(av)}&b=${encodeURIComponent(bv)}`)
      const minCount = Math.min(d.a?.playlist_count || 1, d.b?.playlist_count || 1)
      const overlap = Math.min(100, Math.round((d.shared_playlists / (minCount || 1)) * 100))
      setResult({ ...d, overlap })
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <PvPage>
      <PvTop sub="Taste Tunnel" pill="Shared playlists" />
      <PvHero eyebrow="Collision report" title={result ? `${result.a.name} + ${result.b.name}` : 'Song Collision'}>
        Enter two artists and inspect their shared playlist footprint—and which co-occurring artists bridge them.
      </PvHero>

      <form className="pv-search pv-search-route" onSubmit={e => { e.preventDefault(); search(a, b) }}>
        <div className="pv-search-field"><input value={a} onChange={e => setA(e.target.value)} placeholder="Artist A…" /></div>
        <div className="pv-search-field"><ArrowRight size={15} className="text-[var(--text-low)] shrink-0" /><input value={b} onChange={e => setB(e.target.value)} placeholder="Artist B…" /></div>
        <button disabled={!a.trim() || !b.trim() || loading}>{loading ? 'Working…' : 'Collide'}</button>
      </form>
      <div className="pv-chips">
        <span>Try</span>
        {EXAMPLES.map(ex => <button key={ex.a} onClick={() => { setA(ex.a); setB(ex.b); search(ex.a, ex.b) }}>{ex.a} + {ex.b}</button>)}
      </div>

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/formula-pulse.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Mapping collision zone…</p>
            </div>
          </div>
        )}

        {!result && !loading && !error && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/no-data.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Enter two artists to see where they collide.</p>
            </div>
          </div>
        )}

        {error && !loading && <ErrorSignal detail={error} onRetry={() => search(a, b)}>We couldn’t calculate this collision.</ErrorSignal>}
        {result && !loading && !error && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
              <div className="pv-panel atlas-rise" style={{ '--i': 0 }}>
                <p className="pv-panel-label">Shared reach</p>
                <p className="text-7xl font-extrabold tracking-[-0.04em] leading-none" style={{ color: ACCENT }}>
                  <CountUp value={result.overlap} /><span className="text-3xl align-top">%</span>
                </p>
                <p className="text-[var(--text-mid)] mt-3"><CountUp value={result.shared_playlists} /> shared playlists</p>
              </div>

              <div className="pv-panel atlas-rise" style={{ '--i': 1 }}>
                <p className="pv-panel-label">Collision note</p>
                <div className="grid grid-cols-2 gap-3">
                  {[result.a, result.b].map(x => (
                    <div key={x.name} className="pv-cell">
                      <small>{x.name}</small>
                      <strong>{(x.playlist_count ?? 0).toLocaleString()}</strong>
                      <span className="text-xs text-[var(--text-low)]">playlists{x.rank ? ` · #${x.rank}` : ''}</span>
                    </div>
                  ))}
                </div>
                <p className="text-[var(--text-mid)] text-sm leading-relaxed mt-4">
                  {result.a.name} and {result.b.name} share {result.shared_playlists.toLocaleString()} playlists —
                  about {result.overlap}% of the smaller artist's footprint.
                </p>
              </div>
            </div>

            {result.bridge_artists?.length > 0 && (
              <div className="pv-panel atlas-rise" style={{ '--i': 2 }}>
                <p className="pv-panel-label">Bridge artists — who connects them</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {result.bridge_artists.slice(0, 9).map((br, i) => (
                    <Link key={br.name} to="/compass" state={{ artist: br.name }} className="pv-cell hover:bg-white/[0.06] transition-colors" title={`Open ${br.name} in Compass`}>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                        <div className="min-w-0">
                          <p className="text-[var(--text-hi)] text-sm truncate">{br.name}</p>
                          <p className="text-[var(--text-low)] text-xs">{(br.shared_with_a ?? 0).toLocaleString()} / {(br.shared_with_b ?? 0).toLocaleString()} shared edges</p>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </PvPage>
  )
}
