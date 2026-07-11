import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { Search } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero } from '../components/Premium'
import { errorMessage, getJson } from '../lib/api'

const A_COLOR = '#5AC8FA'
const B_COLOR = '#FB923C'
const EXAMPLES = [
  { a: 'Drake', b: 'Taylor Swift' },
  { a: 'Kendrick Lamar', b: 'Radiohead' },
  { a: 'Billie Eilish', b: 'The Weeknd' },
]

const prettyVerdict = (v) => (v || '').replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())

function Subject({ data, color, label }) {
  return (
    <div className="pv-panel atlas-rise" style={{ '--i': label === 'A' ? 0 : 2 }}>
      <p className="pv-panel-label" style={{ color }}>Subject {label}</p>
      <p className="text-[var(--text-hi)] text-2xl font-bold truncate">{data.name}</p>
      <div className="grid grid-cols-2 gap-3 mt-4">
        <div className="pv-cell"><small>Playlists</small><strong>{(data.playlist_count ?? 0).toLocaleString()}</strong></div>
        <div className="pv-cell"><small>Archive %</small><strong style={{ color }}>{data.pct}%</strong></div>
      </div>
      <p className="text-xs text-[var(--text-low)] mt-3">Reach rank #{data.rank}</p>
      {data.top_tracks?.length > 0 && (
        <div className="mt-4">
          <p className="text-[var(--text-low)] text-[11px] uppercase tracking-[0.14em] mb-2">Top tracks</p>
          {data.top_tracks.slice(0, 4).map((t, i) => (
            <p key={t + i} className="text-[var(--text-mid)] text-sm py-1 truncate">{t}</p>
          ))}
        </div>
      )}
    </div>
  )
}

export default function OverlapArena() {
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.a && s?.b) { setA(s.a); setB(s.b); search(s.a, s.b) }
  }, [location.state])

  const search = async (av, bv) => {
    if (!av?.trim() || !bv?.trim()) return
    setLoading(true)
    setResult(null)
    try {
      setResult(await getJson(`/api/overlap-arena?a=${encodeURIComponent(av)}&b=${encodeURIComponent(bv)}`))
    } catch (e) {
      setResult({ a: { name: av, playlist_count: 0, pct: 0, rank: '—', top_tracks: [] }, b: { name: bv, playlist_count: 0, pct: 0, rank: '—', top_tracks: [] }, shared_playlists: 0, overlap_pct: 0, verdict: 'unknown', _demo: true, _error: errorMessage(e) })
    } finally {
      setLoading(false)
    }
  }

  return (
    <PvPage>
      <PvTop sub="Artist Observatory" pill="Overlap arena" />
      <PvHero eyebrow="Comparative dossier" title={result ? `${result.a.name} / ${result.b.name}` : 'Overlap Arena'}>
        Compare two artists by reach and the share of playlists where their audiences overlap.
      </PvHero>

      <form className="pv-search" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr) auto' }} onSubmit={e => { e.preventDefault(); search(a, b) }}>
        <div className="pv-search-field"><Search size={15} className="text-[var(--text-low)] shrink-0" /><input value={a} onChange={e => setA(e.target.value)} placeholder="Artist A…" /></div>
        <div className="pv-search-field"><Search size={15} className="text-[var(--text-low)] shrink-0" /><input value={b} onChange={e => setB(e.target.value)} placeholder="Artist B…" /></div>
        <button disabled={!a.trim() || !b.trim() || loading}>{loading ? 'Working…' : 'Compare'}</button>
      </form>
      <div className="pv-chips">
        <span>Try</span>
        {EXAMPLES.map(ex => <button key={ex.a} onClick={() => { setA(ex.a); setB(ex.b); search(ex.a, ex.b) }}>{ex.a} / {ex.b}</button>)}
      </div>

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/formula-pulse.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Computing artist overlap…</p>
            </div>
          </div>
        )}

        {!result && !loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/no-data.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Enter two artists to compare their playlist territory.</p>
            </div>
          </div>
        )}

        {result && !loading && (
          <div className="space-y-4">
            {result._demo && <p className="text-xs text-[var(--warning)]">Sample data — {result._error || 'live endpoint unavailable'}.</p>}
            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_260px_minmax(0,1fr)] gap-4 items-start">
              <Subject data={result.a} color={A_COLOR} label="A" />

              <div className="pv-panel text-center atlas-rise" style={{ '--i': 1 }}>
                <p className="pv-panel-label">Shared territory</p>
                <p className="text-6xl font-extrabold tracking-[-0.05em] text-[var(--text-hi)]"><CountUp value={result.shared_playlists} /></p>
                <p className="text-[var(--text-low)] text-xs uppercase tracking-[0.14em] mt-1">shared playlists</p>
                <p className="text-4xl font-extrabold mt-5" style={{ color: '#3DDC97' }}><CountUp value={result.overlap_pct} decimals={1} />%</p>
                <p className="text-[var(--text-low)] text-xs uppercase tracking-[0.14em]">overlap</p>
                <p className="mt-5 inline-block px-3 py-1.5 rounded-full text-sm" style={{ color: '#3DDC97', background: '#3DDC9718', border: '1px solid #3DDC9744' }}>{prettyVerdict(result.verdict)}</p>
              </div>

              <Subject data={result.b} color={B_COLOR} label="B" />
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
