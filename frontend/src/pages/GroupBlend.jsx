import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, X, Shuffle, User } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#B08CF8'

export default function GroupBlend() {
  const [inputs, setInputs] = useState(['', ''])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const addInput = () => { if (inputs.length < 6) setInputs([...inputs, '']) }
  const removeInput = (i) => setInputs(inputs.filter((_, j) => j !== i))
  const update = (i, val) => setInputs(inputs.map((v, j) => j === i ? val : v))

  const blend = async () => {
    const valid = inputs.filter(v => v.trim())
    if (valid.length < 2) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      setResult(await getJson('/api/group-blend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artists: valid }),
      }))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const validCount = inputs.filter(v => v.trim()).length

  return (
    <PvPage>
      <PvTop sub="Taste Tunnel" pill="2–6 artists" />
      <PvHero eyebrow="Consensus route" title="Group Blend">
        Find the artists that sit in the intersection of several people's tastes — a shared lane, not the safest average.
      </PvHero>

      <div className="max-w-6xl space-y-4">
        <div className="pv-panel">
          <p className="pv-panel-label">Participant artists</p>
          <div className="space-y-2">
            {inputs.map((val, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="flex-1 flex items-center rounded-xl bg-black/25 border border-[var(--hairline)] overflow-hidden focus-within:border-[color:var(--accent)] transition-colors">
                  <User size={14} className="ml-3 text-[var(--text-low)] shrink-0" />
                  <input
                    value={val}
                    onChange={e => update(i, e.target.value)}
                    placeholder={`Artist ${i + 1}`}
                    className="flex-1 bg-transparent px-3 py-2.5 text-sm text-[var(--text-hi)] placeholder:text-[var(--text-low)] outline-none"
                  />
                </div>
                {inputs.length > 2 && (
                  <button onClick={() => removeInput(i)} className="text-[var(--text-low)] hover:text-[var(--danger)] transition-colors"><X size={15} /></button>
                )}
              </div>
            ))}
          </div>
          <div className="flex items-center gap-3 mt-4">
            {inputs.length < 6 && (
              <button onClick={addInput} className="flex items-center gap-1.5 text-xs text-[var(--text-mid)] hover:text-[var(--text-hi)]"><Plus size={13} /> Add artist</button>
            )}
            <button
              onClick={blend}
              disabled={validCount < 2 || loading}
              className="ml-auto inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold disabled:opacity-40"
              style={{ background: ACCENT, color: '#0B0616' }}
            >
              <Shuffle size={15} />{loading ? 'Blending…' : 'Blend'}
            </button>
          </div>
        </div>

        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 260 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/loading-cubes.json" className="w-32 h-32 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Finding intersection zones…</p>
            </div>
          </div>
        )}

        {error && !loading && <ErrorSignal detail={error} onRetry={blend}>We couldn’t calculate this group blend.</ErrorSignal>}
        {result && !loading && !error && (
          <div className="grid grid-cols-1 xl:grid-cols-[300px_minmax(0,1fr)] gap-4 items-start">
            <div className="pv-panel atlas-rise" style={{ '--i': 0 }}>
              <p className="pv-panel-label">Blend summary</p>
              <p className="text-7xl font-extrabold tracking-[-0.04em]" style={{ color: ACCENT }}>
                <CountUp value={result.compatibility_pct} decimals={1} /><span className="text-2xl align-top">%</span>
              </p>
              <p className="text-[var(--text-low)] text-xs uppercase tracking-[0.14em] mt-1">shared-neighborhood coverage</p>
              <div className="flex flex-wrap gap-2 mt-5">
                {result.input_artists.map(a => (
                  <span key={a} className="text-xs px-2.5 py-1 rounded-full text-[var(--text-mid)] border border-[var(--hairline)]">{a}</span>
                ))}
              </div>
            </div>

            <div className="pv-panel atlas-rise" style={{ '--i': 1 }}>
              <p className="pv-panel-label">Shared lane — {result.blend_artists?.length || 0} artists</p>
              <div className="space-y-px">
                {(result.blend_artists || []).map((a, i) => (
                  <Link
                    key={a.name}
                    to="/compass"
                    state={{ artist: a.name }}
                    className="grid grid-cols-[auto_minmax(0,1fr)_auto_100px] gap-4 items-center py-2.5 px-2 rounded-lg border-b border-[var(--hairline)] last:border-0 hover:bg-white/[0.04]"
                    title={`Open ${a.name} in Compass`}
                  >
                    <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                    <span className="text-[var(--text-hi)] text-sm truncate">{a.name}</span>
                    <span className="text-xs text-[var(--text-low)]">{(a.playlist_count ?? 0).toLocaleString()}</span>
                    <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${Math.round((a.blend_score || 0) * 100)}%`, background: ACCENT }} />
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
