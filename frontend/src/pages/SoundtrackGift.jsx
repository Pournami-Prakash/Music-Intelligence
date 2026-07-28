import { useEffect, useState } from 'react'
import { Gift } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import ShareResult from '../components/ShareResult'
import { PvPage, PvTop, PvHero } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson, readSharedParam } from '../lib/api'

const ACCENT = '#5AC8FA'

const ROLE_COLORS = {
  opener: '#5AC8FA', build: '#3DDC97', anchor: '#B08CF8', peak: '#FB923C',
  wind_down: '#94A3B8', closer: '#FF7A9C', bonus: '#F5C451',
}

const PROMPTS = [
  'A playlist for my friend who just moved across the world',
  'Something for someone going through a breakup but ready to heal',
  'A birthday gift for my dad who loves classic rock',
  'For someone who needs to feel less alone at 3am',
]

export default function SoundtrackGift() {
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const generate = async (targetPrompt = prompt) => {
    if (!targetPrompt.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await getJson('/api/soundtrack-gift', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: targetPrompt }),
      })
      setResult({ ...data, brief: targetPrompt })
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const sharedBrief = readSharedParam('brief')
    if (sharedBrief) {
      setPrompt(sharedBrief)
      generate(sharedBrief)
    }
  }, [])

  return (
    <PvPage>
      <PvTop sub="Song World" pill="Gift arc" />
      <PvHero eyebrow="Recipient brief" title="Soundtrack Gift">
        Describe a person or moment. The page assembles a playlist arc — openers, anchors, peaks, and closers.
      </PvHero>

      <div className="max-w-6xl space-y-4">
        <div className="pv-panel">
          <p className="pv-panel-label">Write the brief</p>
          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="Describe who this playlist is for, the moment, or the feeling…"
            rows={3}
            maxLength={500}
            aria-describedby="gift-brief-limit"
            className="w-full rounded-xl bg-black/25 border border-[var(--hairline)] px-4 py-3 text-sm text-[var(--text-hi)] placeholder:text-[var(--text-low)] outline-none focus:border-[color:var(--accent)] transition-colors resize-none"
          />
          <p id="gift-brief-limit" className="mt-2 text-right text-[10px] text-[var(--text-low)]">{prompt.length}/500</p>
          <div className="flex flex-wrap gap-2 mt-3">
            {PROMPTS.map(p => (
              <button key={p} onClick={() => setPrompt(p)} className="text-xs text-[var(--text-mid)] border border-[var(--hairline)] rounded-full px-3 py-1.5 hover:text-[var(--text-hi)] transition-colors">
                {p}
              </button>
            ))}
          </div>
          <button
            onClick={() => generate()}
            disabled={!prompt.trim() || loading}
            className="mt-4 inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold disabled:opacity-40"
            style={{ background: ACCENT, color: '#04121A' }}
          >
            <Gift size={15} />
            {loading ? 'Composing…' : 'Generate soundtrack'}
          </button>
        </div>

        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 260 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/audio-wave.json" className="w-48 h-24 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Sequencing the track arc…</p>
            </div>
          </div>
        )}

        {error && !loading && <ErrorSignal detail={error} onRetry={() => generate()}>We couldn’t compose this soundtrack.</ErrorSignal>}
        {result && !loading && !error && (
          <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
            <div className="pv-panel atlas-rise" style={{ '--i': 0 }}>
              <p className="pv-panel-label">Gift sleeve</p>
              <p className="text-[var(--text-hi)] text-2xl font-bold leading-tight">{result.playlist_name}</p>
              <div className="flex flex-wrap gap-2 mt-4">
                {result.habitat && <span className="text-xs px-2.5 py-1 rounded-full capitalize" style={{ color: ACCENT, background: `${ACCENT}18`, border: `1px solid ${ACCENT}44` }}>{result.habitat}</span>}
                {result.energy && <span className="text-xs px-2.5 py-1 rounded-full capitalize text-[var(--text-mid)] border border-[var(--hairline)]">{result.energy} energy</span>}
                {result.llm_powered && <span className="text-xs px-2.5 py-1 rounded-full text-[var(--text-mid)] border border-[var(--hairline)]">AI-curated</span>}
                {result.route_score != null && <span className="text-xs px-2.5 py-1 rounded-full text-[var(--text-mid)] border border-[var(--hairline)]">{Math.round(result.route_score * 100)}% arc fit</span>}
              </div>
              {result.reasoning && <p className="text-[var(--text-mid)] text-sm mt-4 leading-relaxed">{result.reasoning}</p>}
              <p className="text-[var(--text-low)] text-sm mt-4 italic leading-relaxed">“{result.brief}”</p>
              <ShareResult params={{ brief: result.brief }} className="mt-5 inline-flex" />
            </div>

            <div className="pv-panel atlas-rise" style={{ '--i': 1 }}>
              <p className="pv-panel-label">Emotional arc — {result.tracks?.length || 0} tracks</p>
              <div className="space-y-px">
                {(result.tracks || []).map((t, i) => (
                  <div key={`${t.title}-${i}`} className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-4 items-center py-3 border-b border-[var(--hairline)] last:border-0">
                    <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                    <div className="min-w-0">
                      <p className="text-[var(--text-hi)] text-sm truncate">{t.title}</p>
                      <p className="text-[var(--text-low)] text-xs truncate">{t.artist}</p>
                      <p className="text-[var(--text-low)] text-[10px] mt-1">energy {t.energy?.toFixed(2)} → target {t.target_energy?.toFixed(2)}</p>
                    </div>
                    <span className="text-xs font-medium capitalize" style={{ color: ROLE_COLORS[t.role] || 'var(--text-mid)' }}>{String(t.role || '').replace('_', ' ')}</span>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs leading-relaxed text-[var(--text-low)]">
                Ordered from {result.meta?.candidate_count?.toLocaleString()} context-matched tracks with FMA audio evidence.
              </p>
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
