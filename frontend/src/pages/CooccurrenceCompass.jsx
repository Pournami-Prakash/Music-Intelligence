import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import OrbitField from '../components/OrbitField'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvSearch, PvChips, PvPanel } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#B08CF8'
const SUGGESTIONS = ['Drake', 'The Weeknd', 'Taylor Swift', 'Radiohead', 'Kendrick Lamar']

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

export default function CooccurrenceCompass() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState(null)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.artist) { setQuery(s.artist); search(s.artist) }
  }, [location.state])

  const search = async (q) => {
    if (!q.trim()) return
    setLoading(true)
    setSelected(null)
    setResult(null)
    setError(null)
    try {
      const data = await getJson(`/api/compass/${encodeURIComponent(q)}`)
      setResult({ center: data.center, neighbors: data.neighbors })
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const strongest = result?.neighbors?.[0]
  const picked = selected || strongest

  return (
    <PvPage>
      <PvTop sub="Taste Tunnel" pill="Artist co-occurrence" />
      <PvHero eyebrow="Co-occurrence field" title={result?.center?.title || 'Co-occurrence Compass'}>
        Put one artist at the center and inspect the other artists most often pulled into the same playlists.
      </PvHero>

      <PvSearch value={query} onChange={setQuery} onSubmit={() => search(query)} placeholder="Artist name…" button="Open orbit" loading={loading} icon />
      <PvChips items={SUGGESTIONS} onPick={s => { setQuery(s); search(s) }} />

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 340 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/radar.json" className="w-44 h-44 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Plotting shared playlist gravity…</p>
            </div>
          </div>
        )}

        {!result && !loading && !error && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 340 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/radar.json" className="w-44 h-44 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Search an artist to open their playlist orbit field.</p>
            </div>
          </div>
        )}

        {error && !loading && <ErrorSignal detail={error} onRetry={() => search(query)}>We couldn’t open this artist’s co-occurrence field.</ErrorSignal>}
        {result && !loading && !error && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)] gap-4 items-start">
              <PvPanel label="Subject file" className="atlas-rise" style={{ '--i': 0 }}>
                <p className="text-[var(--text-hi)] text-3xl font-extrabold tracking-[-0.03em]">{result.center.title}</p>
                <p className="text-[var(--text-low)] text-xs uppercase tracking-[0.14em] mt-1">playlist gravity center</p>
                <div className="mt-5">
                  <Bar label="strongest neighbor (reference)" value={(strongest?.strength || 0) * 100} color={ACCENT} />
                  <Bar label="selected relative pull" value={(picked?.strength || 0) * 100} color="#5AC8FA" />
                </div>
              </PvPanel>

              <PvPanel label="Orbit field" className="atlas-rise" style={{ '--i': 1 }}>
                <div className="rounded-2xl bg-black/30 border border-[var(--hairline)] p-2" style={{ minHeight: 480 }}>
                  <OrbitField center={result.center.title} neighbors={result.neighbors} accent={ACCENT} selected={picked} onSelect={setSelected} />
                </div>
              </PvPanel>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_340px] gap-4">
              <PvPanel label="Co-occurrence ledger" className="atlas-rise" style={{ '--i': 2 }}>
                <div className="space-y-px">
                  {result.neighbors.slice(0, 8).map((n, i) => (
                    <div
                      key={`${n.title}-${i}`}
                      onClick={() => setSelected(n)}
                      className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] gap-4 items-center py-2.5 px-2 rounded-lg cursor-pointer border-b border-[var(--hairline)] last:border-0 hover:bg-white/[0.04]"
                      style={selected === n ? { background: `${ACCENT}18` } : undefined}
                    >
                      <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                      <span className="text-[var(--text-hi)] text-sm truncate">{n.title}</span>
                      <span className="text-xs text-[var(--text-mid)]">{(n.strength * 100).toFixed(0)}%</span>
                      <button
                        onClick={e => { e.stopPropagation(); setQuery(n.title); search(n.title) }}
                        className="text-xs font-mono uppercase tracking-[0.1em]"
                        style={{ color: ACCENT }}
                      >
                        recenter
                      </button>
                    </div>
                  ))}
                </div>
              </PvPanel>

              <PvPanel label="Selected node" className="atlas-rise" style={{ '--i': 3 }}>
                {picked && (
                  <>
                    <h3 className="text-2xl font-bold text-[var(--text-hi)]">{picked.title}</h3>
                    <p className="mt-2 text-sm text-[var(--text-mid)]">Appears near {result.center.title} through repeated playlist co-placement.</p>
                    <div className="mt-5"><Bar label="playlist pull" value={picked.strength * 100} color={ACCENT} /></div>
                  </>
                )}
              </PvPanel>
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
