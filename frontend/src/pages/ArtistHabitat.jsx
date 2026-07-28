import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvSearch, PvChips, PvPanel } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson, readSharedParam, replaceSharedParams } from '../lib/api'

const HABITATS = [
  { key: 'gym', label: 'Gym / Workout', color: '#3DDC97', code: 'GYM' },
  { key: 'heartbreak', label: 'Heartbreak', color: '#FF7A9C', code: 'BRK' },
  { key: 'road_trip', label: 'Road Trip', color: '#B08CF8', code: 'RD' },
  { key: 'party', label: 'Party', color: '#FB923C', code: 'PTY' },
  { key: 'study', label: 'Study / Focus', color: '#5AC8FA', code: 'STD' },
  { key: 'chill', label: 'Chill / Vibe', color: '#F5C451', code: 'CLL' },
  { key: 'throwback', label: 'Throwback', color: '#94A3B8', code: 'TBK' },
  { key: 'sleep', label: 'Sleep / Wind Down', color: '#7C8CF8', code: 'SLP' },
]

const SUGGESTIONS = ['Drake', 'Taylor Swift', 'Kendrick Lamar', 'The Weeknd', 'Radiohead']

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

export default function ArtistHabitat() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    const sharedArtist = readSharedParam('artist')
    const initialArtist = s?.artist || sharedArtist
    if (initialArtist) { setQuery(initialArtist); search(initialArtist) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await getJson(`/api/artist-habitat/${encodeURIComponent(q)}`)
      const flat = {}
      for (const h of HABITATS) flat[h.key] = data.habitats?.[h.key]?.pct ?? 0
      setResult({ artist: data.artist || q, habitats: flat, playlist_count: data.playlist_count })
      replaceSharedParams({ artist: data.artist || q })
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const topHabitat = result
    ? HABITATS.slice().sort((a, b) => (result.habitats[b.key] || 0) - (result.habitats[a.key] || 0))[0]
    : null

  return (
    <PvPage>
      <PvTop sub="Artist Observatory" pill="Habitat radar" />
      <PvHero eyebrow="Habitat dossier" title={result?.artist || 'Artist Habitat'}>
        Map the playlist rooms an artist occupies — workout, heartbreak, road trip, study, sleep, and other real-life uses.
      </PvHero>

      <PvSearch
        value={query}
        onChange={setQuery}
        onSubmit={() => search(query)}
        placeholder="Artist name…"
        button="Map habitat"
        loading={loading}
        icon
      />
      <PvChips items={SUGGESTIONS} onPick={s => { setQuery(s); search(s) }} />

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/radar.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Mapping playlist habitats…</p>
            </div>
          </div>
        )}

        {error && !loading && <ErrorSignal detail={error} onRetry={() => search(query)}>We couldn’t map this artist’s habitat.</ErrorSignal>}
        {result && !loading && (
          <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
            <div className="space-y-4">
              {topHabitat && (
                <PvPanel label="Primary habitat" className="atlas-rise" style={{ '--i': 0 }}>
                  <div className="flex items-center gap-4">
                    <div
                      className="grid place-items-center shrink-0"
                      style={{ width: 54, height: 54, borderRadius: 14, background: `${topHabitat.color}22`, border: `1px solid ${topHabitat.color}55` }}
                    >
                      <span style={{ color: topHabitat.color }} className="font-mono text-xs font-bold">{topHabitat.code}</span>
                    </div>
                    <div>
                      <p className="text-[var(--text-hi)] text-xl font-bold">{topHabitat.label}</p>
                      <p className="text-[var(--text-mid)] text-xs mt-1">
                        {Math.round(result.habitats[topHabitat.key])}% of playlists where {result.artist} appears
                      </p>
                    </div>
                  </div>
                </PvPanel>
              )}
            </div>
            <PvPanel label="Measured playlist habitats" className="atlas-rise" style={{ '--i': 1 }}>
              <p className="mb-5 text-sm text-[var(--text-mid)]">Share of playlists containing {result.artist} whose titles signal each use case. Categories can overlap.</p>
              {HABITATS.slice().sort((a, b) => (result.habitats[b.key] || 0) - (result.habitats[a.key] || 0)).map(h => (
                <Bar key={h.key} label={h.label} value={result.habitats[h.key] || 0} color={h.color} />
              ))}
            </PvPanel>
          </div>
        )}

        {!result && !loading && !error && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 340 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/radar.json" className="w-44 h-44 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Search an artist to see which playlist climate they occupy.</p>
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
