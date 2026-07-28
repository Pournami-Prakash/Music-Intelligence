import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero, PvSearch, PvChips, PvPanel } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#B08CF8'
const SUGGESTIONS = ['Taylor Swift', 'Kendrick Lamar', 'Radiohead', 'Beyoncé', 'Frank Ocean']

const TIERS = [
  { min: 90, label: 'Top-decile reach' },
  { min: 75, label: 'High playlist reach' },
  { min: 50, label: 'Above-median reach' },
  { min: 25, label: 'Focused playlist reach' },
  { min: 0, label: 'Long-tail reach' },
]
const tierLabel = (s) => (TIERS.find(t => s >= t.min) || TIERS[TIERS.length - 1]).label

function Bar({ label, value, color }) {
  return (
    <div className="mb-3 last:mb-0">
      <div className="flex justify-between text-sm mb-1.5">
        <span className="text-[var(--text-mid)]">{label}</span>
        <span style={{ color }}>{Math.round(value)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.min(100, value)}%`, background: color }} />
      </div>
    </div>
  )
}

export default function MainCharacter() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.query) { setQuery(s.query); search(s.query) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await getJson(`/api/main-character/${encodeURIComponent(q)}`)
      setResult({
        artist: data.artist || q,
        score: Math.round(data.score ?? 0),
        percentile: data.percentile,
        rank: data.rank,
        listeners: data.listeners,
        pct: data.pct,
        top_tracks: data.top_tracks || [],
        colony: data.colony || [],
      })
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <PvPage>
      <PvTop sub="Artist Observatory" pill="Reach percentile" />
      <PvHero eyebrow="Playlist reach" title={result?.artist || 'Playlist Reach Score'}>
        Place an artist in the archive by how many playlists contain them, then inspect their strongest co-occurrence neighbors.
      </PvHero>

      <PvSearch value={query} onChange={setQuery} onSubmit={() => search(query)} placeholder="Artist name…" button="Score persona" loading={loading} icon />
      <PvChips items={SUGGESTIONS} onPick={s => { setQuery(s); search(s) }} />

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/trending-upward.lottie" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Calculating playlist-reach percentile…</p>
            </div>
          </div>
        )}

        {!result && !loading && !error && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/trending-upward.lottie" className="w-32 h-32 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Search an artist to measure their playlist reach.</p>
            </div>
          </div>
        )}

        {error && !loading && <ErrorSignal detail={error} onRetry={() => search(query)}>We couldn’t calculate this artist’s reach percentile.</ErrorSignal>}
        {result && !loading && !error && (
          <div className="grid grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)] gap-4 items-start">
            <PvPanel label="Persona file" className="atlas-rise" style={{ '--i': 0 }}>
              <p className="font-extrabold text-8xl leading-none tracking-[-0.05em]" style={{ color: ACCENT }}>
                <CountUp value={result.score} />
              </p>
              <p className="text-[var(--text-low)] text-xs uppercase tracking-[0.16em] mt-1">playlist-reach percentile</p>
              <p className="text-[var(--text-hi)] text-2xl font-bold mt-4">{tierLabel(result.score)}</p>
              <p className="text-[var(--text-mid)] text-xs mt-2 leading-relaxed">
                This is the artist’s percentile among the 10,000 most-playlisted artists. It does not measure influence or artistic importance.
              </p>
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div className="pv-cell"><small>Reach percentile</small><strong>{result.percentile != null ? `${Math.round(result.percentile)}th` : '—'}</strong></div>
                <div className="pv-cell"><small>Reach rank</small><strong>#{result.rank}</strong></div>
              </div>
            </PvPanel>

            <div className="space-y-4">
              {result.top_tracks.length > 0 && (
                <PvPanel label="Signature tracks" className="atlas-rise" style={{ '--i': 1 }}>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {result.top_tracks.slice(0, 6).map((t, i) => (
                      <div key={t} className="flex items-center gap-3 py-2">
                        <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                        <span className="text-[var(--text-hi)] text-sm truncate">{t}</span>
                      </div>
                    ))}
                  </div>
                </PvPanel>
              )}

              {result.colony.length > 0 && (
                <PvPanel label="Colony — artists in orbit" className="atlas-rise" style={{ '--i': 2 }}>
                  {result.colony.slice(0, 6).map(c => (
                    <Link key={c.name} to="/compass" state={{ artist: c.name }} className="block hover:opacity-80" title={`Open ${c.name} in Compass`}>
                      <Bar label={c.name} value={c.overlap_pct} color={ACCENT} />
                    </Link>
                  ))}
                </PvPanel>
              )}
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
