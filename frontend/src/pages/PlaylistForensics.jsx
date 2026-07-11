import { useState } from 'react'
import { Fingerprint } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero } from '../components/Premium'
import { errorMessage, getJson } from '../lib/api'

const SAMPLE = `Blinding Lights
As It Was
Levitating
Anti-Hero
Flowers
Kill Bill
Unholy
Vampire
Cruel Summer
good 4 u`

export default function PlaylistForensics() {
  const [text, setText] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const analyze = async () => {
    const tracks = text.split('\n').map(t => t.trim()).filter(Boolean)
    if (tracks.length === 0) return
    setLoading(true)
    setResult(null)
    try {
      setResult(await getJson('/api/forensics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tracks }),
      }))
    } catch (e) {
      setResult({ organic_pct: 0, editorial_pct: 0, verdict: 'error', verdict_detail: `Live endpoint unavailable — ${errorMessage(e)}.`, signals: [], _demo: true })
    } finally {
      setLoading(false)
    }
  }

  const organic = result ? Math.round(result.organic_pct) : 0
  const editorial = result ? Math.round(result.editorial_pct) : 0
  const verdictColor = organic > 50 ? '#3DDC97' : '#FF7A9C'

  return (
    <PvPage>
      <PvTop sub="Deep Map" pill="Curation forensics" />
      <PvHero eyebrow="Curation forensics" title="Playlist Forensics">
        Paste a playlist's track titles (one per line) and inspect whether the selection looks organic or editorial-heavy.
      </PvHero>

      <div className="max-w-6xl space-y-4">
        <div className="pv-panel">
          <div className="flex items-center justify-between mb-3">
            <p className="pv-panel-label" style={{ marginBottom: 0 }}>Track list</p>
            <button onClick={() => setText(SAMPLE)} className="text-xs text-[var(--text-mid)] hover:text-[var(--text-hi)]">Load sample</button>
          </div>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder={"One track title per line…\nBlinding Lights\nAs It Was\nLevitating"}
            rows={6}
            className="w-full rounded-xl bg-black/25 border border-[var(--hairline)] px-4 py-3 text-sm text-[var(--text-hi)] placeholder:text-[var(--text-low)] outline-none focus:border-[color:var(--accent)] transition-colors resize-none"
          />
          <button
            onClick={analyze}
            disabled={!text.trim() || loading}
            className="mt-4 inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold disabled:opacity-40"
            style={{ background: 'var(--accent)', color: '#04140D' }}
          >
            <Fingerprint size={15} />{loading ? 'Inspecting…' : 'Analyze'}
          </button>
        </div>

        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 240 }}>
            <div className="text-center"><LottiePlayer src="/assets/formula-pulse.json" className="w-36 h-36 mx-auto" /><p className="mt-2 text-[var(--text-mid)]">Scoring against editorial density…</p></div>
          </div>
        )}

        {result && !loading && (
          <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
            <div className="pv-panel atlas-rise" style={{ '--i': 0 }}>
              <p className="pv-panel-label">Verdict</p>
              {result._demo && <p className="mb-3 text-xs text-[var(--warning)]">{result.verdict_detail}</p>}
              <p className="text-2xl font-bold capitalize" style={{ color: verdictColor }}>{String(result.verdict || '').replace(/_/g, ' ')}</p>
              <div className="mt-5 space-y-3">
                <div>
                  <div className="flex justify-between text-sm mb-1.5"><span className="text-[var(--text-mid)]">organic</span><span style={{ color: '#3DDC97' }}>{organic}%</span></div>
                  <div className="h-1.5 rounded-full bg-white/10 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${organic}%`, background: '#3DDC97' }} /></div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1.5"><span className="text-[var(--text-mid)]">editorial</span><span style={{ color: '#FF7A9C' }}>{editorial}%</span></div>
                  <div className="h-1.5 rounded-full bg-white/10 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${editorial}%`, background: '#FF7A9C' }} /></div>
                </div>
              </div>
            </div>

            <div className="pv-panel atlas-rise" style={{ '--i': 1 }}>
              <p className="pv-panel-label">Signal explanation</p>
              {!result._demo && <p className="text-[var(--text-mid)] leading-relaxed">{result.verdict_detail}</p>}
              {result.signals?.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
                  {result.signals.map(s => (
                    <div key={s.label} className="pv-cell">
                      <small>{s.label}</small>
                      <strong>{s.value}</strong>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
