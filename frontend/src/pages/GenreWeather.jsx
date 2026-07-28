import { useEffect, useState } from 'react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage } from '../lib/api'

export default function GenreWeather() {
  const [genres, setGenres] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/data/genre-weather.json')
      .then(r => r.ok ? r.json() : Promise.reject(new Error('unreachable')))
      .then(d => {
        if (d.genres?.length) {
          setGenres(d.genres)
          setSelectedId(d.genres[0].id)
        }
        else { setError('The genre projection contains no readable regions.') }
      })
      .catch(e => {
        setError(errorMessage(e))
      })
  }, [])

  if (error) {
    return (
      <PvPage>
        <PvTop sub="Deep Map" pill="Static projection" />
        <PvHero eyebrow="Playlist-cluster proximity" title="Genre Neighborhoods">
          See which genre clusters appear near each other in the corpus.
        </PvHero>
        <div className="max-w-6xl"><ErrorSignal detail={error}>We couldn’t load the genre projection.</ErrorSignal></div>
      </PvPage>
    )
  }

  if (!genres) {
    return (
      <PvPage>
        <PvTop sub="Deep Map" pill="Static projection" />
        <PvHero eyebrow="Playlist-cluster proximity" title="Genre Neighborhoods">
          See which genre clusters appear near each other in the corpus.
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

  const metrics = shown.slice(0, 6)
  const selected = shown.find(genre => genre.id === selectedId) || shown[0]
  const neighbors = shown
    .filter(genre => genre.id !== selected.id)
    .map(genre => ({ ...genre, distance: Math.hypot(genre.cx - selected.cx, genre.cy - selected.cy) }))
    .sort((a, b) => a.distance - b.distance)
    .slice(0, 5)

  return (
    <PvPage>
      <PvTop sub="Deep Map" pill="Static projection" />
      <PvHero eyebrow="Playlist-cluster proximity" title="Genre Neighborhoods">
        Compare {genres.length} genre regions by relative position, track evidence, and nearest neighbors.
      </PvHero>

      <div className="max-w-6xl grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-4">
        <PvPanel label="Genre projection" className="atlas-rise" style={{ '--i': 0 }}>
          <div className="mb-4 grid grid-cols-3 gap-3 text-[10px] text-[var(--text-low)]">
            <span><b className="text-[var(--text-hi)]">Position</b><br />relative cluster proximity</span>
            <span><b className="text-[var(--text-hi)]">Marker size</b><br />track count</span>
            <span><b className="text-[var(--text-hi)]">Direction</b><br />not independently meaningful</span>
          </div>
          <div className="genre-projection" aria-label="Genre-cluster projection">
            <span className="genre-axis genre-axis-x">Projection dimension 1</span>
            <span className="genre-axis genre-axis-y">Projection dimension 2</span>
            {shown.map((g, i) => {
              const s = Math.min(30, Math.max(9, size(g) / 8))
              const isSelected = selected.id === g.id
              return (
                <button
                  key={g.id}
                  className={`genre-point ${isSelected ? 'is-selected' : ''}`}
                  onClick={() => setSelectedId(g.id)}
                  aria-label={`${g.label}, ${g.track_count.toLocaleString()} tracks`}
                  aria-pressed={isSelected}
                  style={{
                    top: `${py(g)}%`,
                    left: `${px(g)}%`,
                    '--point-color': g.color,
                    '--point-size': `${s}px`,
                  }}
                >
                  <i />
                  {(i < 10 || isSelected) && <span>{g.label}</span>}
                </button>
              )
            })}
          </div>
        </PvPanel>

        <div className="space-y-4">
          <PvPanel label="Selected neighborhood" className="atlas-rise" style={{ '--i': 1 }}>
            <p className="text-xl font-bold" style={{ color: selected.color }}>{selected.label}</p>
            <div className="grid grid-cols-2 gap-3 mt-4 pb-4 border-b border-[var(--hairline)]">
              <div>
                <b className="block text-lg text-[var(--text-hi)]">{selected.track_count.toLocaleString()}</b>
                <small className="text-[10px] uppercase tracking-wider text-[var(--text-low)]">tracks</small>
              </div>
              <div>
                <b className="block text-lg text-[var(--text-hi)]">{selected.cluster_count ?? '—'}</b>
                <small className="text-[10px] uppercase tracking-wider text-[var(--text-low)]">clusters</small>
              </div>
            </div>
            <p className="mt-4 mb-2 text-[9px] uppercase tracking-[0.14em] text-[var(--text-low)]">Nearest plotted genres</p>
            <div>
              {neighbors.map((genre, index) => (
                <button
                  key={genre.id}
                  onClick={() => setSelectedId(genre.id)}
                  className="w-full flex items-center justify-between py-2 border-b border-[var(--hairline)] text-left"
                >
                  <span className="text-sm text-[var(--text-mid)]">{index + 1}. {genre.label}</span>
                  <span className="text-[10px] text-[var(--text-low)]">{genre.distance.toFixed(2)} units</span>
                </button>
              ))}
            </div>
          </PvPanel>

          <PvPanel label="Largest evidence bases" className="atlas-rise" style={{ '--i': 2 }}>
            <div className="space-y-3">
              {metrics.map(g => (
                <button key={g.id} onClick={() => setSelectedId(g.id)} className="w-full text-left">
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="text-[var(--text-hi)]">{g.label}</span>
                    <span className="text-[var(--text-mid)]">{g.track_count.toLocaleString()}</span>
                  </div>
                  <div className="h-1 bg-white/10 overflow-hidden">
                    <div className="h-full" style={{ width: `${(g.track_count / maxT) * 100}%`, background: g.color }} />
                  </div>
                </button>
              ))}
            </div>
          </PvPanel>

          <PvPanel label="Interpretation limit" className="atlas-rise" style={{ '--i': 3 }}>
            <p className="text-xs leading-relaxed text-[var(--text-mid)]">
              This is a static projection. Nearby points share cluster context, but the axes do not represent tempo, mood, popularity, or change over time.
            </p>
          </PvPanel>
        </div>
      </div>
    </PvPage>
  )
}
