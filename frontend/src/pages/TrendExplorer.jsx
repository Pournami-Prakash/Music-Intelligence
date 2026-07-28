import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero, PvSearch, PvChips, PvPanel } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#FB923C'
const SUGGESTIONS = ['vibes', 'chill', 'sad', 'aesthetic', 'summer']

export default function TrendExplorer() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.term) { setQuery(s.term); search(s.term) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await getJson(`/api/trend-explorer/${encodeURIComponent(q.trim())}`)
      setResult({
        term: data.term,
        count: data.count,
        pct: parseFloat((data.pct ?? 0).toFixed(2)),
        theme: data.theme,
        variants: data.examples || [],
        related: data.related || [],
      })
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <PvPage>
      <PvTop sub="Vibe Dictionary" pill="Language probe" />
      <PvHero eyebrow="Vocabulary record" title={result?.term || 'Trend Explorer'}>
        Search playlist-title language by frequency, variants, and the related phrases people attach to a word.
      </PvHero>

      <PvSearch value={query} onChange={setQuery} onSubmit={() => search(query)} placeholder="Any word from playlist titles…" button="Explore word" loading={loading} icon />
      <PvChips items={SUGGESTIONS} onPick={s => { setQuery(s); search(s) }} />

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/letters.lottie" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Scanning playlist language…</p>
            </div>
          </div>
        )}

        {!result && !loading && !error && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/letters.lottie" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Search any word from playlist titles to see its cultural gravity.</p>
            </div>
          </div>
        )}

        {error && !loading && <ErrorSignal detail={error} onRetry={() => search(query)}>We couldn’t look up this playlist-title term.</ErrorSignal>}
        {result && !loading && !error && (
          <div className="space-y-4">
            <PvPanel className="atlas-rise" style={{ '--i': 0 }}>
              <p className="font-extrabold leading-[0.82] tracking-[-0.06em] text-[var(--text-hi)] break-words" style={{ fontSize: 'clamp(52px, 10vw, 120px)' }}>“{result.term}”</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-6 max-w-2xl">
                <div className="pv-cell"><small>Playlists</small><strong style={{ color: ACCENT }}><CountUp value={result.count} /></strong></div>
                <div className="pv-cell"><small>Archive share</small><strong style={{ color: ACCENT }}>{result.pct}%</strong></div>
                {result.theme && <div className="pv-cell"><small>Theme</small><strong className="capitalize">{result.theme}</strong></div>}
              </div>
            </PvPanel>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {result.variants.length > 0 && (
                <PvPanel label="Common variants" className="atlas-rise" style={{ '--i': 1 }}>
                  <div className="flex flex-wrap gap-2">
                    {result.variants.map((v, i) => (
                      <span key={v + i} className="text-sm text-[var(--text-mid)] border border-[var(--hairline)] rounded-full px-3 py-1.5">{v}</span>
                    ))}
                  </div>
                </PvPanel>
              )}
              {result.related.length > 0 && (
                <PvPanel label="Related terms" className="atlas-rise" style={{ '--i': 2 }}>
                  <div className="flex flex-wrap gap-2">
                    {result.related.map(r => (
                      <button
                        key={r}
                        onClick={() => { setQuery(r); search(r) }}
                        className="text-sm rounded-full px-3 py-1.5 transition-colors"
                        style={{ color: ACCENT, background: `${ACCENT}14`, border: `1px solid ${ACCENT}44` }}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                </PvPanel>
              )}
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
