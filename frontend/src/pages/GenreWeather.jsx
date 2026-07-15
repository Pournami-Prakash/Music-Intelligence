import { useEffect, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { errorMessage } from '../lib/api'

const DRIFTS = ['atlas-drift-1', 'atlas-drift-2', 'atlas-drift-3', 'atlas-drift-4']

// Fallback if the endpoint is unreachable — keeps the page from breaking.
const FALLBACK = [
  { id: 'hyperpop', label: 'Hyperpop', color: '#FB923C', track_count: 90000, cx: 4, cy: 4 },
  { id: 'phonk', label: 'Phonk', color: '#3DDC97', track_count: 60000, cx: 12, cy: 8 },
  { id: 'shoegaze', label: 'Shoegaze', color: '#5AC8FA', track_count: 30000, cx: 16, cy: 3 },
  { id: 'punk', label: 'Punk revival', color: '#FF7A9C', track_count: 15000, cx: 6, cy: 12 },
]

export default function GenreWeather() {
  const [genres, setGenres] = useState(null)
  const [demo, setDemo] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/data/genre-weather.json')
      .then(r => r.ok ? r.json() : Promise.reject(new Error('unreachable')))
      .then(d => {
        if (d.genres?.length) setGenres(d.genres)
        else { setGenres(FALLBACK); setDemo(true); setError('empty genre list') }
      })
      .catch(e => { setGenres(FALLBACK); setDemo(true); setError(errorMessage(e)) })
  }, [])

  if (!genres) {
    return (
      <PvPage>
        <PvTop sub="Deep Map" pill="Weather system" />
        <PvHero eyebrow="Genre pressure map" title="Genre Weather">
          Read genres as moving systems — drift, pressure, cooling regions, and merge fronts across playlist culture.
        </PvHero>
        <div className="pv-panel max-w-6xl grid place-items-center" style={{ minHeight: 360 }}>
          <div className="text-center">
            <LottiePlayer src="/assets/audio-wave.json" className="w-48 h-24 mx-auto" />
            <p className="mt-2 text-[var(--text-mid)]">Reading genre pressure field…</p>
          </div>
        </div>
      </PvPage>
    )
  }

  // Several genres share a slate fallback color server-side; reassign duplicates
  // from a distinct palette so regions stay visually separable on the map.
  const PALETTE = ['#3DDC97', '#5AC8FA', '#B08CF8', '#F5C451', '#FF7A9C', '#FB923C', '#22D3EE', '#C084FC', '#A3E635', '#38BDF8', '#FB7185', '#E879F9', '#FACC15', '#F97316']
  const usedColors = new Set()
  let paletteIdx = 0
  const shown = [...genres].sort((a, b) => b.track_count - a.track_count).slice(0, 14).map(g => {
    let color = g.color
    if (!color || usedColors.has(color)) {
      while (usedColors.has(PALETTE[paletteIdx % PALETTE.length])) paletteIdx++
      color = PALETTE[paletteIdx % PALETTE.length]
    }
    usedColors.add(color)
    return { ...g, color }
  })
  const xs = shown.map(g => g.cx), ys = shown.map(g => g.cy)
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
  const maxT = Math.max(...shown.map(g => g.track_count))
  const px = g => 7 + ((g.cx - minX) / (maxX - minX || 1)) * 86
  const py = g => 9 + ((g.cy - minY) / (maxY - minY || 1)) * 82
  const size = g => 68 + Math.sqrt(g.track_count / maxT) * 176

  // Real "merge front": the closest pair of large genres in the map.
  let front = null, best = Infinity
  for (let i = 0; i < shown.length; i++) {
    for (let j = i + 1; j < shown.length; j++) {
      const d = Math.hypot(shown[i].cx - shown[j].cx, shown[i].cy - shown[j].cy)
      if (d < best) { best = d; front = [shown[i], shown[j]] }
    }
  }

  const metrics = shown.slice(0, 6)

  return (
    <PvPage>
      <PvTop sub="Deep Map" pill="Weather system" />
      <PvHero eyebrow="Genre pressure map" title="Genre Weather">
        Read genres as moving systems — drift, pressure, and merge fronts across {genres.length} genre regions of playlist culture.
      </PvHero>

      {demo && <p className="max-w-6xl mb-3 text-xs text-[var(--warning)]">Showing sample data — {error || 'live endpoint unavailable'}.</p>}

      <div className="max-w-6xl grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-4">
        <PvPanel label="Pressure field" className="atlas-rise" style={{ '--i': 0 }}>
          <div className="pv-weather">
            {front && (
              <div className="absolute left-6 top-5 z-10 flex items-center gap-3" style={{ color: front[0].color }}>
                <AlertTriangle size={22} />
                <div>
                  <p className="text-[11px] uppercase tracking-[0.16em] font-semibold">Merge front</p>
                  <p className="text-[var(--text-hi)] text-lg font-bold">{front[0].label} / {front[1].label}</p>
                </div>
              </div>
            )}

            {shown.map((g, i) => {
              const s = size(g)
              return (
                <div
                  key={g.id}
                  className="pv-front"
                  style={{
                    width: s, height: s, top: `${py(g)}%`, left: `${px(g)}%`, transform: 'translate(-50%,-50%)',
                    background: `radial-gradient(circle at 40% 35%, ${g.color}55, ${g.color}12 55%, transparent 72%)`,
                    boxShadow: `inset 0 0 60px ${g.color}33`,
                    animation: `${DRIFTS[i % 4]} ${16 + (i % 5) * 3}s ease-in-out infinite`,
                  }}
                >
                  <span className="pv-front-ring" style={{ inset: 0, border: `1px solid ${g.color}55` }} />
                  {s > 108 && <span style={{ color: g.color }}>{g.label}</span>}
                </div>
              )
            })}
          </div>
        </PvPanel>

        <div className="space-y-4">
          <PvPanel label="System pressure" className="atlas-rise" style={{ '--i': 1 }}>
            <div className="space-y-4">
              {metrics.map(g => (
                <div key={g.id}>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-[var(--text-hi)]">{g.label}</span>
                    <span className="text-[var(--text-mid)]">{(g.track_count / 1000).toFixed(0)}k</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${(g.track_count / maxT) * 100}%`, background: g.color }} />
                  </div>
                </div>
              ))}
            </div>
          </PvPanel>

          <PvPanel label="Region ledger" className="atlas-rise" style={{ '--i': 2 }}>
            <div className="space-y-px">
              {shown.slice(0, 8).map(g => (
                <div key={g.id} className="flex justify-between items-center py-2.5 border-b border-[var(--hairline)] last:border-0">
                  <span className="flex items-center gap-2 text-[var(--text-hi)] text-sm">
                    <span style={{ width: 8, height: 8, borderRadius: 999, background: g.color }} />
                    {g.label}
                  </span>
                  <span className="text-xs text-[var(--text-low)]">{g.cluster_count ?? '—'} clusters</span>
                </div>
              ))}
            </div>
          </PvPanel>
        </div>
      </div>
    </PvPage>
  )
}
