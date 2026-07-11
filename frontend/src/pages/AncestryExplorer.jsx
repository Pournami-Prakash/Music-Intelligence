import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero, PvSearch, PvChips, PvPanel } from '../components/Premium'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#7AB89A'
const SUGGESTIONS = ['Radiohead', 'Kendrick Lamar', 'Taylor Swift', 'Daft Punk', 'Frank Ocean']

function ArtistRow({ name, meta, i }) {
  return (
    <Link to="/ancestry" state={{ artist: name }} className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-3 items-center py-2.5 px-2 rounded-lg border-b border-[var(--hairline)] last:border-0 hover:bg-white/[0.04]" title={`Trace ${name}`}>
      <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
      <span className="text-[var(--text-hi)] text-sm truncate">{name}</span>
      {meta && <span className="text-xs" style={{ color: ACCENT }}>{meta}</span>}
    </Link>
  )
}

export default function AncestryExplorer() {
  const [query, setQuery] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.artist) { setQuery(s.artist); search(s.artist) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setData(null)
    try {
      setData(await getJson(`/api/ancestry/${encodeURIComponent(q)}`))
    } catch (e) {
      setData({ artist: q, artist_tags: [], listeners: 0, lastfm_similar: [], ancestors: [], descendants: [], _demo: true, _error: errorMessage(e) })
    } finally {
      setLoading(false)
    }
  }

  return (
    <PvPage>
      <PvTop sub="Deep Map" pill="Influence tree" />
      <PvHero eyebrow="Music ancestry" title={data?.artist || 'Ancestry Explorer'}>
        Search an artist and trace the lineage backward into influences and forward into descendants.
      </PvHero>

      <PvSearch value={query} onChange={setQuery} onSubmit={() => search(query)} placeholder="Artist name…" button="Explore" loading={loading} icon />
      <PvChips items={SUGGESTIONS} onPick={s => { setQuery(s); search(s) }} />

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/loading-cubes.json" className="w-32 h-32 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Tracing lineage…</p>
            </div>
          </div>
        )}

        {!data && !loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/loading-cubes.json" className="w-32 h-32 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Search an artist to explore their lineage.</p>
            </div>
          </div>
        )}

        {data && !loading && (
          <div className="grid grid-cols-1 xl:grid-cols-[300px_minmax(0,1fr)] gap-4 items-start">
            <PvPanel label="Subject file" className="atlas-rise" style={{ '--i': 0 }}>
              {data._demo && <p className="mb-3 text-xs text-[var(--warning)]">Sample data — {data._error || 'live endpoint unavailable'}.</p>}
              <p className="text-2xl font-bold text-[var(--text-hi)]">{data.artist}</p>
              {data.listeners > 0 && <p className="text-[var(--text-mid)] text-sm mt-1"><CountUp value={data.listeners} /> listeners</p>}
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div className="pv-cell"><small>Influences</small><strong>{data.ancestors?.length || 0}</strong></div>
                <div className="pv-cell"><small>Descendants</small><strong>{data.descendants?.length || 0}</strong></div>
              </div>
              {data.artist_tags?.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-4">
                  {data.artist_tags.slice(0, 8).map(t => (
                    <span key={t} className="text-xs px-2.5 py-1 rounded-full" style={{ color: ACCENT, background: `${ACCENT}18`, border: `1px solid ${ACCENT}44` }}>{t}</span>
                  ))}
                </div>
              )}
            </PvPanel>

            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <PvPanel label="← Ancestors (influences)" className="atlas-rise" style={{ '--i': 1 }}>
                  {data.ancestors?.length > 0
                    ? data.ancestors.map((a, i) => <ArtistRow key={a.name || a} name={a.name || a} meta={a.similarity ? `${Math.round(a.similarity * 100)}%` : null} i={i} />)
                    : <p className="text-[var(--text-low)] text-sm">No clear ancestors in this dataset.</p>}
                </PvPanel>

                <PvPanel label="Descendants →" className="atlas-rise" style={{ '--i': 2 }}>
                  {data.descendants?.length > 0
                    ? data.descendants.slice(0, 8).map((d, i) => <ArtistRow key={d.name} name={d.name} meta={d.similarity ? `${Math.round(d.similarity * 100)}%` : null} i={i} />)
                    : <p className="text-[var(--text-low)] text-sm">No descendants found.</p>}
                </PvPanel>
              </div>

              {data.lastfm_similar?.length > 0 && (
                <PvPanel label="Similar artists" className="atlas-rise" style={{ '--i': 3 }}>
                  <div className="flex flex-wrap gap-2">
                    {data.lastfm_similar.map(name => (
                      <Link key={name} to="/ancestry" state={{ artist: name }} className="text-sm px-3 py-1.5 rounded-full text-[var(--text-mid)] border border-[var(--hairline)] hover:text-[var(--text-hi)] transition-colors">{name}</Link>
                    ))}
                  </div>
                </PvPanel>
              )}
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
