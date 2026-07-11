import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { errorMessage, getJson } from '../lib/api'

const MOODS = [
  { key: 'sad', label: 'Sad', color: '#5AC8FA' },
  { key: 'angry', label: 'Angry', color: '#FF7A9C' },
  { key: 'heartbreak', label: 'Heartbreak', color: '#B08CF8' },
  { key: 'anxious', label: 'Anxious', color: '#FB923C' },
  { key: 'lonely', label: 'Lonely', color: '#94A3B8' },
]

export default function MoodContradiction() {
  const [mood, setMood] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.mood) selectMood(s.mood)
  }, [location.state])

  const selectMood = async (key) => {
    setMood(key)
    setLoading(true)
    setData(null)
    try {
      setData(await getJson(`/api/mood-contradiction?mood=${encodeURIComponent(key)}&limit=12`))
    } catch (e) {
      setData({ _demo: true, _error: errorMessage(e), mood: key, contrary_moods: [], mood_playlists: 0, contrary_playlists: 0, tracks: [] })
    } finally {
      setLoading(false)
    }
  }

  const activeMood = MOODS.find(m => m.key === mood)
  const accent = activeMood?.color || '#B08CF8'
  const lead = data?.tracks?.[0]
  const contraryLabel = data?.contrary_moods?.[0] || 'other'

  return (
    <PvPage>
      <PvTop sub="Song World" pill="Mismatch detector" />
      <PvHero eyebrow="Intent versus reality" title="Mood Contradiction">
        Find songs whose playlist context says one emotion while their real public use points somewhere else.
      </PvHero>

      <div className="max-w-6xl">
        <div className="flex flex-wrap gap-2 mb-4">
          {MOODS.map(m => (
            <button
              key={m.key}
              onClick={() => selectMood(m.key)}
              className="px-4 py-2 rounded-full text-sm border transition-colors"
              style={{
                borderColor: mood === m.key ? m.color : 'var(--hairline)',
                background: mood === m.key ? `${m.color}22` : 'rgba(255,255,255,0.03)',
                color: mood === m.key ? m.color : 'var(--text-mid)',
              }}
            >
              {m.label}
            </button>
          ))}
        </div>

        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/audio-wave.json" className="w-48 h-24 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Comparing playlist intent with song reality…</p>
            </div>
          </div>
        )}

        {!mood && !loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/no-data.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Choose an emotional room to reveal songs filed under the wrong feeling.</p>
            </div>
          </div>
        )}

        {data?._demo && !loading && (
          <p className="text-xs text-[var(--warning)] mb-3">Live endpoint unavailable for this mood — {data._error || 'unknown error'}.</p>
        )}

        {lead && !loading && (
          <div className="space-y-4">
            <PvPanel className="atlas-rise" style={{ '--i': 0 }}>
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_1px_1fr] gap-6">
                <div className="flex flex-col justify-between min-h-[300px]">
                  <div>
                    <p className="font-mono text-[11px] uppercase tracking-[0.2em]" style={{ color: accent }}>playlist context</p>
                    <h2 className="mt-3 text-4xl sm:text-5xl font-extrabold tracking-[-0.03em] text-[var(--text-hi)] capitalize">{activeMood.label} playlists</h2>
                    <p className="text-[var(--text-mid)] mt-4">{data.mood_playlists?.toLocaleString()} editorial playlists filed under “{mood}”.</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 mt-6">
                    <div className="pv-cell"><small>Lead track</small><strong className="text-lg">{lead.title}</strong><span className="text-xs text-[var(--text-mid)]">{lead.artist}</span></div>
                    <div className="pv-cell"><small>“{mood}” appearances</small><strong style={{ color: accent }}>{lead.mood_appearances}</strong></div>
                  </div>
                </div>

                <div className="hidden lg:block w-px bg-[var(--hairline)]" />

                <div className="flex flex-col justify-between min-h-[300px]">
                  <div>
                    <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--warning)]">actual reality</p>
                    <h2 className="mt-3 text-4xl sm:text-5xl font-extrabold tracking-[-0.03em] text-[var(--text-hi)] capitalize">{contraryLabel} rooms</h2>
                    <div className="mt-5 flex items-start gap-3 rounded-xl border p-4" style={{ borderColor: 'var(--warning)', background: 'rgba(245,196,81,0.08)' }}>
                      <AlertTriangle size={18} className="text-[var(--warning)] mt-0.5 shrink-0" />
                      <p className="text-sm text-[var(--text-mid)] leading-relaxed">
                        “{lead.title}” shows up in {lead.contrary_appearances} {contraryLabel}-type playlists but only {lead.mood_appearances} {mood} ones — a {lead.contradiction_score}× mismatch.
                      </p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 mt-6">
                    <div className="pv-cell"><small>Counter-room hits</small><strong>{lead.contrary_appearances}</strong></div>
                    <div className="pv-cell"><small>Contradiction</small><strong style={{ color: accent }}>{lead.contradiction_score}×</strong></div>
                  </div>
                </div>
              </div>
            </PvPanel>

            <PvPanel label="Other contradictions" className="atlas-rise" style={{ '--i': 1 }}>
              <div className="space-y-px">
                {data.tracks.slice(1).map(song => (
                  <div key={song.title + song.artist} className="grid grid-cols-[minmax(0,2fr)_1fr_auto] gap-4 items-center py-3 border-b border-[var(--hairline)] last:border-0">
                    <div className="min-w-0">
                      <p className="text-[var(--text-hi)] text-sm font-medium truncate">{song.title}</p>
                      <p className="text-[var(--text-low)] text-xs truncate">{song.artist}</p>
                    </div>
                    <span className="text-xs text-[var(--text-mid)]">{song.contrary_appearances} vs {song.mood_appearances}</span>
                    <span className="text-sm font-semibold text-right" style={{ color: accent }}>{song.contradiction_score}×</span>
                  </div>
                ))}
              </div>
            </PvPanel>
          </div>
        )}
      </div>
    </PvPage>
  )
}
