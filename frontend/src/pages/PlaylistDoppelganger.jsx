import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero, PvSearch, PvChips, PvPanel } from '../components/Premium'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#B08CF8'
const SUGGESTIONS = ['Drake', 'Phoebe Bridgers', 'Radiohead', 'Tyler, the Creator', 'SZA']

export default function PlaylistDoppelganger() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.artist || s?.query) { const q = s.artist || s.query; setQuery(q); search(q) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setResult(null)
    try {
      setResult(await getJson(`/api/doppelganger/${encodeURIComponent(q)}`))
    } catch (e) {
      setResult({ artist: q, track_count: 0, doppelgangers: [], _demo: true, _error: errorMessage(e) })
    } finally {
      setLoading(false)
    }
  }

  const nearest = result?.doppelgangers?.[0]

  return (
    <PvPage>
      <PvTop sub="Taste Tunnel" pill="Embedding twins" />
      <PvHero eyebrow="Doppelganger search" title={result?.artist || 'Artist Doppelganger'}>
        Enter an artist and find their sonic doppelgängers — the artists sitting closest in the track-embedding space.
      </PvHero>

      <PvSearch value={query} onChange={setQuery} onSubmit={() => search(query)} placeholder="Artist name…" button="Find twins" loading={loading} icon />
      <PvChips items={SUGGESTIONS} onPick={s => { setQuery(s); search(s) }} />

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/search.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Finding your doppelgängers…</p>
            </div>
          </div>
        )}

        {!result && !loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/search.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Search an artist to find their sonic twins.</p>
            </div>
          </div>
        )}

        {result && !loading && (
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px] gap-4 items-start">
            <PvPanel label="Closest twins" className="atlas-rise" style={{ '--i': 0 }}>
              {result._demo && <p className="mb-3 text-xs text-[var(--warning)]">Sample data — {result._error || 'live endpoint unavailable'}.</p>}
              <div className="space-y-px">
                {(result.doppelgangers || []).map((d, i) => (
                  <Link
                    key={d.name + i}
                    to="/compass"
                    state={{ artist: d.name }}
                    className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-4 items-center py-3 px-2 rounded-lg border-b border-[var(--hairline)] last:border-0 hover:bg-white/[0.04]"
                    title={`Open ${d.name} in Compass`}
                  >
                    <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                    <span className="min-w-0">
                      <span className="block text-[var(--text-hi)] text-sm truncate">{d.name}</span>
                      {d.tags?.length > 0 && <span className="block text-[var(--text-low)] text-xs truncate">{d.tags.slice(0, 4).join(' · ')}</span>}
                    </span>
                    <span className="text-sm font-semibold" style={{ color: ACCENT }}>{(d.similarity * 100).toFixed(0)}%</span>
                  </Link>
                ))}
                {result.doppelgangers?.length === 0 && <p className="text-[var(--text-low)] text-sm">No doppelgängers found for this artist.</p>}
              </div>
            </PvPanel>

            <PvPanel label="Twin signature" className="atlas-rise" style={{ '--i': 1 }}>
              <p className="text-[var(--text-hi)] text-2xl font-bold">{result.artist}</p>
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div className="pv-cell"><small>Tracks analysed</small><strong><CountUp value={result.track_count} /></strong></div>
                <div className="pv-cell"><small>Nearest twin</small><strong style={{ color: ACCENT }}>{nearest ? `${(nearest.similarity * 100).toFixed(0)}%` : '—'}</strong></div>
              </div>
              {nearest && <p className="text-[var(--text-mid)] text-sm mt-4">Closest match: <span className="text-[var(--text-hi)]">{nearest.name}</span></p>}
            </PvPanel>
          </div>
        )}
      </div>
    </PvPage>
  )
}
