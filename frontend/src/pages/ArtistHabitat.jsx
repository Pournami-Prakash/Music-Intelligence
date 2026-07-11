import { useState, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import * as d3 from 'd3'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvSearch, PvChips, PvPanel } from '../components/Premium'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#3DDC97'

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

const MOCK_DATA = {
  'Drake': { gym: 22, heartbreak: 31, road_trip: 18, party: 47, study: 9, chill: 38, throwback: 12, sleep: 4 },
  'Taylor Swift': { gym: 8, heartbreak: 58, road_trip: 24, party: 19, study: 14, chill: 33, throwback: 22, sleep: 11 },
  'Kendrick Lamar': { gym: 34, heartbreak: 14, road_trip: 22, party: 29, study: 18, chill: 21, throwback: 16, sleep: 3 },
  'The Weeknd': { gym: 19, heartbreak: 41, road_trip: 27, party: 38, study: 11, chill: 44, throwback: 9, sleep: 8 },
  'Radiohead': { gym: 3, heartbreak: 28, road_trip: 19, party: 6, study: 41, chill: 37, throwback: 18, sleep: 22 },
}

const DEFAULT_HABITAT = { gym: 18, heartbreak: 24, road_trip: 20, party: 32, study: 15, chill: 28, throwback: 14, sleep: 7 }
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
  const svgRef = useRef(null)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.artist) { setQuery(s.artist); search(s.artist) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const data = await getJson(`/api/artist-habitat/${encodeURIComponent(q)}`)
      const flat = {}
      for (const h of HABITATS) flat[h.key] = data.habitats?.[h.key]?.pct ?? 0
      setResult({ artist: data.artist || q, habitats: flat, playlist_count: data.playlist_count })
    } catch (e) {
      setResult({ artist: q, habitats: MOCK_DATA[q] || DEFAULT_HABITAT, _demo: true, _error: errorMessage(e) })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!result || !svgRef.current) return
    const el = svgRef.current
    const W = el.getBoundingClientRect().width || 620
    const H = Math.min(W * 0.68, 540)
    const cx = W / 2, cy = H / 2
    const R = Math.min(W, H) * 0.38
    el.setAttribute('width', W)
    el.setAttribute('height', H)

    const svg = d3.select(el)
    svg.selectAll('*').remove()

    const keys = HABITATS.map(h => h.key)
    const vals = keys.map(k => result.habitats[k] || 0)
    const maxVal = Math.max(...vals, 1)
    const angleSlice = (2 * Math.PI) / keys.length
    const grid = 'rgba(255,255,255,0.09)'

    ;[0.25, 0.5, 0.75, 1].forEach(f => {
      svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', R * f)
        .attr('fill', 'none').attr('stroke', grid).attr('stroke-width', 1)
    })

    keys.forEach((k, i) => {
      const angle = angleSlice * i - Math.PI / 2
      const x = cx + Math.cos(angle) * R
      const y = cy + Math.sin(angle) * R
      svg.append('line').attr('x1', cx).attr('y1', cy).attr('x2', x).attr('y2', y)
        .attr('stroke', grid).attr('stroke-width', 1)

      const lx = cx + Math.cos(angle) * (R + 18)
      const ly = cy + Math.sin(angle) * (R + 18)
      svg.append('text').attr('x', lx).attr('y', ly).attr('text-anchor', 'middle').attr('dominant-baseline', 'middle')
        .attr('font-size', '10px').attr('fill', '#6B7280').attr('font-family', 'JetBrains Mono')
        .text(HABITATS[i].code)
    })

    const points = keys.map((k, i) => {
      const angle = angleSlice * i - Math.PI / 2
      const r = ((result.habitats[k] || 0) / maxVal) * R
      return [cx + Math.cos(angle) * r, cy + Math.sin(angle) * r]
    })
    svg.append('polygon')
      .attr('points', points.map(p => p.join(',')).join(' '))
      .attr('fill', ACCENT).attr('fill-opacity', 0.16)
      .attr('stroke', ACCENT).attr('stroke-width', 2)

    points.forEach(([px, py], i) => {
      svg.append('circle').attr('cx', px).attr('cy', py).attr('r', 4)
        .attr('fill', HABITATS[i].color).attr('stroke', '#050505').attr('stroke-width', 1.5)
    })
  }, [result])

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

        {result?._demo && !loading && (
          <p className="mb-3 text-xs text-[var(--warning)]">Showing sample data — {result._error || 'live endpoint unavailable'}.</p>
        )}
        {result && !loading && (
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-4 items-start">
            <PvPanel label="Habitat radar" className="atlas-rise" style={{ '--i': 0 }}>
              <svg ref={svgRef} className="w-full" style={{ minHeight: 380 }} />
            </PvPanel>

            <div className="space-y-4">
              {topHabitat && (
                <PvPanel label="Primary habitat" className="atlas-rise" style={{ '--i': 1 }}>
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

              <PvPanel label="All habitats" className="atlas-rise" style={{ '--i': 2 }}>
                {HABITATS.slice().sort((a, b) => (result.habitats[b.key] || 0) - (result.habitats[a.key] || 0)).map(h => (
                  <Bar key={h.key} label={h.label} value={result.habitats[h.key] || 0} color={h.color} />
                ))}
              </PvPanel>
            </div>
          </div>
        )}

        {!result && !loading && (
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
