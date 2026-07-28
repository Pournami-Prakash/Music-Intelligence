import { useState, useEffect, useCallback } from 'react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { errorMessage } from '../lib/api'

const MOODS = ['sad', 'happy', 'gym', 'party', 'study', 'sleep', 'chill']
const MOOD_COLORS = {
  sad: '#5AC8FA', happy: '#F5C451', gym: '#3DDC97',
  party: '#FB923C', study: '#B08CF8', sleep: '#94A3B8', chill: '#22D3EE',
}

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

export default function GuiltyPleasureMap() {
  const [mood, setMood] = useState('sad')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    setSelected(null)
    fetch('/data/mood-contradiction.json')
      .then(r => r.ok ? r.json() : Promise.reject(new Error('Context-comparison evidence is unavailable.')))
      .then(all => {
        if (!all[mood]) throw new Error(`No context-comparison evidence exists for ${mood}.`)
        setData(all[mood])
        setLoading(false)
      })
      .catch(e => { setError(errorMessage(e)); setLoading(false) })
  }, [mood])

  useEffect(() => { load() }, [load])

  const accent = MOOD_COLORS[mood] || '#F5C451'
  const maxContra = data?.tracks?.length ? Math.max(...data.tracks.map(t => t.contrary_appearances)) : 1
  const maxMood = data?.tracks?.length ? Math.max(...data.tracks.map(t => t.mood_appearances)) : 1

  return (
    <PvPage>
      <PvTop sub="Song World" pill="Context ledger" />
      <PvHero eyebrow="Cross-context record" title="Context Switchers">
        Compare tracks that appear in one keyword-defined playlist context and in its declared counterpart.
      </PvHero>

      <div className="max-w-6xl">
        <div className="flex flex-wrap gap-2 mb-4">
          {MOODS.map(m => (
            <button
              key={m}
              onClick={() => setMood(m)}
              className="px-4 py-2 rounded-full text-sm border capitalize transition-colors"
              style={{
                borderColor: mood === m ? MOOD_COLORS[m] : 'var(--hairline)',
                background: mood === m ? `${MOOD_COLORS[m]}22` : 'rgba(255,255,255,0.03)',
                color: mood === m ? MOOD_COLORS[m] : 'var(--text-mid)',
              }}
            >
              {m}
            </button>
          ))}
        </div>

        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/audio-wave.json" className="w-48 h-24 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Scanning {mood} playlists for shared tracks…</p>
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="pv-panel text-center" style={{ padding: 40 }}>
            <p className="text-[var(--text-mid)]">Couldn’t load context-comparison data for {mood} playlists.</p>
            <button onClick={load} className="pv-link mt-4 inline-block px-6" style={{ color: accent }}>Try again</button>
          </div>
        )}

        {!loading && !error && (
          <div className="grid grid-cols-1 xl:grid-cols-[330px_minmax(0,1fr)] gap-4 items-start">
            <PvPanel label={selected ? 'Selected track' : 'Context key'} className="atlas-rise" style={{ '--i': 0 }}>
              {selected ? (
                <>
                  <p className="text-[var(--text-hi)] text-xl font-bold">{selected.title}</p>
                  <p className="text-[var(--text-mid)] text-sm">{selected.artist}</p>
                  <div className="mt-4 space-y-1 text-sm text-[var(--text-mid)]">
                    <div>Appears in <strong style={{ color: accent }}>{selected.mood_appearances}</strong> {mood} playlists</div>
                    <div>Also in <strong style={{ color: '#FF7A9C' }}>{selected.contrary_appearances}</strong> comparison-context playlists</div>
                    <div>Context ratio: <strong className="text-[var(--text-hi)]">{selected.contradiction_score.toFixed(2)}×</strong></div>
                  </div>
                  <div className="mt-5">
                    <Bar label="comparison-context pull" value={(selected.contrary_appearances / maxContra) * 100} color="#FF7A9C" />
                    <Bar label={`${mood} presence`} value={(selected.mood_appearances / maxMood) * 100} color={accent} />
                  </div>
                </>
              ) : (
                <p className="text-[var(--text-mid)] text-sm leading-relaxed">
                  Pick a track from the ledger to see how it straddles contradictory playlist contexts.
                  {data && (
                    <span className="block mt-3 text-[var(--text-low)]">
                      {data.mood_playlists} {mood} playlists × {data.contrary_playlists} contrary playlists
                    </span>
                  )}
                </p>
              )}
            </PvPanel>

            <PvPanel label={`${mood} context switchers — ${data?.tracks?.length ?? '…'} tracks`} className="atlas-rise" style={{ '--i': 1 }}>
              {data?.tracks?.length > 0 ? (
                <div className="space-y-px">
                  {data.tracks.map((t, i) => (
                    <button
                      key={`${t.title}-${t.artist}`}
                      onClick={() => setSelected(t)}
                      className="w-full grid grid-cols-[auto_minmax(0,1fr)_auto] gap-4 items-center py-2.5 px-2 rounded-lg text-left border-b border-[var(--hairline)] last:border-0 hover:bg-white/[0.04] transition-colors"
                      style={selected === t ? { background: `${accent}18` } : undefined}
                    >
                      <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                      <span className="min-w-0">
                        <span className="block text-sm text-[var(--text-hi)] truncate">{t.title}</span>
                        <span className="block text-xs text-[var(--text-low)] truncate">{t.artist}</span>
                      </span>
                      <span className="text-right text-xs">
                        <span style={{ color: accent }}>{t.mood_appearances}</span>
                        <span className="text-[var(--text-low)]"> / </span>
                        <span style={{ color: '#FF7A9C' }}>{t.contrary_appearances}</span>
                        <span className="block font-mono text-[var(--text-mid)]">{t.contradiction_score.toFixed(1)}×</span>
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-[var(--text-low)] text-sm">No cross-context tracks were found for this title group.</p>
              )}
            </PvPanel>
          </div>
        )}
      </div>
    </PvPage>
  )
}
