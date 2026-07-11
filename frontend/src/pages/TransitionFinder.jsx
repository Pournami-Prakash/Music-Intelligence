import { useState, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import LottiePlayer from '../components/LottiePlayer'
import TrackAutocomplete from '../components/TrackAutocomplete'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { getJson } from '../lib/api'

const BRIDGE_COLORS = ['#5AC8FA', '#3DDC97', '#B08CF8', '#FB923C', '#22D3EE']
const EXAMPLES = [
  { fromTitle: 'No Surprises', toTitle: 'Mr. Brightside' },
  { fromTitle: 'HUMBLE.', toTitle: 'Bohemian Rhapsody' },
  { fromTitle: 'The Sound of Silence', toTitle: 'Mr. Brightside' },
]

export default function TransitionFinder() {
  const [fromTitle, setFromTitle] = useState('')
  const [toTitle, setToTitle] = useState('')
  const [fromUri, setFromUri] = useState(null)
  const [toUri, setToUri] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const location = useLocation()

  const search = useCallback(async (fUri, tUri) => {
    if (!fUri || !tUri) return
    setLoading(true); setResult(null); setError(null)
    try {
      setResult(await getJson(`/api/transition-finder?from_uri=${encodeURIComponent(fUri)}&to_uri=${encodeURIComponent(tUri)}&limit=5`))
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTitles = useCallback(async (from, to) => {
    setFromTitle(from); setToTitle(to)
    setFromUri(null); setToUri(null); setResult(null); setError(null)
    try {
      const [rA, rB] = await Promise.all([
        fetch(`/api/search-tracks?q=${encodeURIComponent(from)}&limit=1`).then(r => r.json()),
        fetch(`/api/search-tracks?q=${encodeURIComponent(to)}&limit=1`).then(r => r.json()),
      ])
      const uriA = rA.results?.[0]?.uri
      const uriB = rB.results?.[0]?.uri
      if (uriA) setFromUri(uriA)
      if (uriB) setToUri(uriB)
      if (uriA && uriB) search(uriA, uriB)
    } catch { /* user sees empty state */ }
  }, [search])

  useEffect(() => {
    const s = location.state
    if (s?.from && s?.to) loadTitles(s.from, s.to)
  }, [location.state, loadTitles])

  return (
    <PvPage>
      <PvTop sub="Taste Tunnel" pill="Mix route" />
      <PvHero eyebrow="Transition evidence" title="Transition Finder">
        Choose two songs. The atlas proposes bridge tracks that make the jump feel natural inside real playlist culture.
      </PvHero>

      <form className="pv-search" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr) auto' }} onSubmit={e => { e.preventDefault(); search(fromUri, toUri) }}>
        <div className="pv-search-field">
          <TrackAutocomplete value={fromTitle} onChange={v => { setFromTitle(v); setFromUri(null) }} onSelect={item => { setFromTitle(item.title); setFromUri(item.uri) }} placeholder="Starting song…" />
        </div>
        <div className="pv-search-field">
          <TrackAutocomplete value={toTitle} onChange={v => { setToTitle(v); setToUri(null) }} onSelect={item => { setToTitle(item.title); setToUri(item.uri) }} placeholder="Destination song…" />
        </div>
        <button disabled={!fromUri || !toUri || loading}>{loading ? 'Working…' : 'Find bridge'}</button>
      </form>

      {!fromUri && fromTitle.length > 1 && (
        <p className="text-[var(--text-low)] text-xs mb-3">Pick a track from the dropdown to get its ID</p>
      )}

      <div className="pv-chips">
        <span>Try</span>
        {EXAMPLES.map(ex => <button key={ex.fromTitle} onClick={() => loadTitles(ex.fromTitle, ex.toTitle)}>{ex.fromTitle} → {ex.toTitle}</button>)}
      </div>

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/audio-wave.json" className="w-48 h-24 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Finding bridge tracks between both songs…</p>
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="pv-panel text-center" style={{ padding: 40 }}>
            <p className="text-[var(--text-mid)]">Couldn't build a route between these two tracks.</p>
            <button onClick={() => search(fromUri, toUri)} className="pv-link mt-4 inline-block px-6" style={{ color: '#B08CF8' }}>Try again</button>
          </div>
        )}

        {!result && !loading && !error && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/turntable.json" className="w-48 h-32 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Select two tracks from the autocomplete and press Find bridge.</p>
            </div>
          </div>
        )}

        {result && !loading && (
          <div className="space-y-4">
            <PvPanel label="Mix route" className="atlas-rise" style={{ '--i': 0 }}>
              <div className="grid grid-cols-1 xl:grid-cols-[200px_minmax(0,1fr)_200px] gap-4 items-center">
                <div className="pv-cell text-center">
                  <small style={{ color: '#3DDC97' }}>start</small>
                  <strong className="text-base leading-tight mt-1">{result.from.title}</strong>
                  <span className="text-xs text-[var(--text-low)]">{result.from.artist}</span>
                </div>
                <div>
                  {result.bridges.length === 0 ? (
                    <p className="text-[var(--text-mid)] text-sm text-center">No bridge tracks found in the embedding space.</p>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      {result.bridges.slice(0, 3).map((b, i) => (
                        <div key={b.uri} className="rounded-xl border border-[var(--hairline)] bg-black/25 p-4">
                          <p className="text-[var(--text-low)] text-[10px] uppercase tracking-[0.16em]">Bridge {i + 1}</p>
                          <p className="text-lg font-bold mt-2 leading-tight" style={{ color: BRIDGE_COLORS[i] }}>{b.title}</p>
                          <p className="text-[var(--text-low)] text-xs mt-1">{b.artist}</p>
                          {b.chart_peak && <p className="text-xs text-[var(--text-mid)] mt-2">Chart peak #{b.chart_peak}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="pv-cell text-center">
                  <small style={{ color: '#B08CF8' }}>finish</small>
                  <strong className="text-base leading-tight mt-1">{toTitle}</strong>
                </div>
              </div>
            </PvPanel>

            {result.bridges.length > 0 && (
              <PvPanel label="All bridge candidates" className="atlas-rise" style={{ '--i': 1 }}>
                <div className="space-y-px">
                  {result.bridges.map((b, i) => (
                    <div key={b.uri} className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-4 items-center py-3 border-b border-[var(--hairline)] last:border-0">
                      <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                      <div className="min-w-0">
                        <p className="text-[var(--text-hi)] text-sm truncate">{b.title}</p>
                        <p className="text-[var(--text-low)] text-xs truncate">{b.artist}</p>
                      </div>
                      <span className="text-xs text-[var(--text-mid)]">{b.chart_peak ? `#${b.chart_peak}` : '—'}</span>
                    </div>
                  ))}
                </div>
              </PvPanel>
            )}
          </div>
        )}
      </div>
    </PvPage>
  )
}
