import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ArrowRight, Search } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero, PvChips, PvPanel } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#B08CF8'
const SUGGESTIONS = [['Drake', 'Radiohead'], ['Taylor Swift', 'Kendrick Lamar'], ['Beyonce', 'Radiohead'], ['Daft Punk', 'Frank Ocean']]

export default function SixDegrees() {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.from && s?.to) { setFrom(s.from); setTo(s.to); search(s.from, s.to) }
  }, [location.state])

  const search = async (a, b) => {
    if (!a.trim() || !b.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const params = new URLSearchParams({ from_artist: a, to_artist: b })
      setResult(await getJson(`/api/six-degrees?${params}`))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const withShared = result?.path?.filter(n => n.shared) || []
  const strongest = [...withShared].sort((a, b) => b.shared - a.shared)[0]
  const last = result?.path?.[result.path.length - 1]

  return (
    <PvPage>
      <PvTop sub="Taste Tunnel" pill="Artist route" />
      <PvHero eyebrow="Path evidence" title="Six Degrees">
        Trace the shortest route found inside each artist’s top-100 co-occurrence neighborhood.
      </PvHero>

      <form className="pv-search pv-search-route" onSubmit={e => { e.preventDefault(); search(from, to) }}>
        <div className="pv-search-field"><Search size={15} className="text-[var(--text-low)] shrink-0" /><input value={from} onChange={e => setFrom(e.target.value)} placeholder="From artist…" /></div>
        <div className="pv-search-field"><ArrowRight size={15} className="text-[var(--text-low)] shrink-0" /><input value={to} onChange={e => setTo(e.target.value)} placeholder="To artist…" /></div>
        <button disabled={!from.trim() || !to.trim() || loading}>{loading ? 'Working…' : 'Find path'}</button>
      </form>
      <PvChips items={SUGGESTIONS} onPick={([a, b]) => { setFrom(a); setTo(b); search(a, b) }} />

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/loading-cubes.json" className="w-32 h-32 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Walking the playlist graph…</p>
            </div>
          </div>
        )}

        {!result && !loading && !error && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/radar.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Pick two artists and open the route between their listening worlds.</p>
            </div>
          </div>
        )}

        {error && !loading && <ErrorSignal detail={error} onRetry={() => search(from, to)}>We couldn’t find a route between these artists.</ErrorSignal>}
        {result && !loading && !error && (
          <div className="space-y-4">
            <PvPanel className="atlas-rise" style={{ '--i': 0 }}>
              <div className="grid grid-cols-1 lg:grid-cols-[200px_minmax(0,1fr)] gap-6 items-start">
                <div className="pv-cell text-center" style={{ alignSelf: 'start' }}>
                  <p className="text-6xl font-extrabold tracking-[-0.05em]" style={{ color: ACCENT }}><CountUp value={result.hops} /></p>
                  <p className="text-[var(--text-low)] text-xs uppercase tracking-[0.14em] mt-1">playlist hops</p>
                </div>
                <div className="space-y-2">
                  {result.path.map((node, i) => (
                    <div key={`${node.name}-${i}`} className="grid grid-cols-[36px_minmax(0,1fr)_auto] gap-3 items-center rounded-xl border border-[var(--hairline)] bg-black/20 px-4 py-3">
                      <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                      <div className="min-w-0">
                        <p className="text-[var(--text-hi)] text-lg font-bold truncate">{node.name}</p>
                        <p className="text-[var(--text-low)] text-xs">{i === 0 ? 'origin artist' : i === result.path.length - 1 ? 'destination artist' : 'bridge artist'}</p>
                      </div>
                      <p className="text-right text-xs text-[var(--text-mid)]">{node.shared ? `${node.shared.toLocaleString()} shared` : 'start'}</p>
                    </div>
                  ))}
                </div>
              </div>
            </PvPanel>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <PvPanel label="Start" className="atlas-rise" style={{ '--i': 1 }}>
                <p className="text-[var(--text-hi)] text-xl font-bold">{result.path[0].name}</p>
                <Link to="/artist-ubiquity" state={{ artist: result.path[0].name }} className="pv-link mt-4">Open ubiquity</Link>
              </PvPanel>
              <PvPanel label="Strongest bridge" className="atlas-rise" style={{ '--i': 2 }}>
                <p className="text-[var(--text-hi)] text-xl font-bold">{strongest?.name || '—'}</p>
                {strongest && <p className="text-[var(--text-mid)] text-sm mt-1">{strongest.shared.toLocaleString()} shared playlists</p>}
                {strongest && <Link to="/compass" state={{ artist: strongest.name }} className="pv-link mt-4">Open in Compass</Link>}
              </PvPanel>
              <PvPanel label="Destination" className="atlas-rise" style={{ '--i': 3 }}>
                <p className="text-[var(--text-hi)] text-xl font-bold">{last?.name}</p>
                <Link to="/artist-ubiquity" state={{ artist: last?.name }} className="pv-link mt-4">Open ubiquity</Link>
              </PvPanel>
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
