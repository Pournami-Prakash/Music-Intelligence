import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero, PvSearch, PvChips, PvPanel } from '../components/Premium'
import { errorMessage, getJson } from '../lib/api'

const SUGGESTIONS = ['vibes', 'chill', 'sad songs', 'summer', 'workout']

function meterColor(s) { return s > 90 ? '#FF7A9C' : s > 70 ? '#FB923C' : s > 50 ? '#F5C451' : '#3DDC97' }
function meterLabel(s) { return s > 90 ? 'Critically generic' : s > 70 ? 'Very common' : s > 50 ? 'Middling' : 'Actually original' }

export default function PlaylistRoast() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.title) { setQuery(s.title); search(s.title) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setResult(null)
    try {
      setResult(await getJson(`/api/roast?title=${encodeURIComponent(q)}`))
    } catch (e) {
      setResult({ title: q, genericness: 0, verdict: `Live endpoint unavailable — ${errorMessage(e)}.`, word_scores: [], examples: [], rare_words: [], similar_count: 0, _demo: true })
    } finally {
      setLoading(false)
    }
  }

  const g = result ? Math.round(result.genericness) : 0
  const color = meterColor(g)

  return (
    <PvPage>
      <PvTop sub="Vibe Dictionary" pill="Verdict file" />
      <PvHero eyebrow="Name audit" title={result?.title || 'Playlist Roast'}>
        Enter a playlist title and see how common, generic, or accidentally original it is across the archive.
      </PvHero>

      <PvSearch value={query} onChange={setQuery} onSubmit={() => search(query)} placeholder="Your playlist title…" button="Roast" loading={loading} icon />
      <PvChips items={SUGGESTIONS} onPick={s => { setQuery(s); search(s) }} />

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/search.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Cross-checking a million playlist names…</p>
            </div>
          </div>
        )}

        {!result && !loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/search.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Enter a playlist title and get a citation from the name archive.</p>
            </div>
          </div>
        )}

        {result && !loading && (
          <div className="space-y-4">
            {result._demo && <p className="text-xs text-[var(--warning)]">{result.verdict}</p>}
            <div className="grid grid-cols-1 xl:grid-cols-[300px_minmax(0,1fr)] gap-4 items-start">
              <PvPanel label="Title citation" className="atlas-rise" style={{ '--i': 0 }}>
                <p className="text-6xl font-extrabold tracking-[-0.04em]" style={{ color }}><CountUp value={g} /><span className="text-2xl align-top">%</span></p>
                <p className="text-xs uppercase tracking-[0.14em] mt-1" style={{ color }}>{meterLabel(g)}</p>
                <p className="text-[var(--text-mid)] text-sm mt-4"><CountUp value={result.similar_count} /> similar titles in the archive</p>
              </PvPanel>

              <PvPanel label="Verdict" className="atlas-rise" style={{ '--i': 1 }}>
                <p className="text-3xl sm:text-5xl font-extrabold leading-[0.95] tracking-[-0.04em] text-[var(--text-hi)] break-words">“{result.title}”</p>
                {!result._demo && <p className="text-[var(--text-mid)] text-base sm:text-lg italic mt-5 max-w-3xl">{result.verdict}</p>}
                <div className="mt-6 max-w-md">
                  <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${g}%`, background: color }} />
                  </div>
                </div>
              </PvPanel>
            </div>

            {result.word_scores?.length > 0 && (
              <PvPanel label="Word breakdown" className="atlas-rise" style={{ '--i': 2 }}>
                <div className="space-y-3">
                  {result.word_scores.map(w => (
                    <div key={w.word}>
                      <div className="flex justify-between text-sm mb-1.5">
                        <span className="text-[var(--text-hi)]">{w.word} <span className="text-[var(--text-low)] text-xs">· {w.theme} · {w.count.toLocaleString()}×</span></span>
                        <span style={{ color: meterColor(w.score) }}>{Math.round(w.score)}%</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${Math.min(100, w.score)}%`, background: meterColor(w.score) }} />
                      </div>
                    </div>
                  ))}
                </div>
              </PvPanel>
            )}

            {result.examples?.length > 0 && (
              <PvPanel label="Real playlists with this name" className="atlas-rise" style={{ '--i': 3 }}>
                <div className="flex flex-wrap gap-2">
                  {result.examples.map((e, i) => (
                    <span key={e + i} className="text-sm text-[var(--text-mid)] border border-[var(--hairline)] rounded-full px-3 py-1.5">{e}</span>
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
