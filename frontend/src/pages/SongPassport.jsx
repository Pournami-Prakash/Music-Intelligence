import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import LottiePlayer from '../components/LottiePlayer'
import TrackAutocomplete from '../components/TrackAutocomplete'
import { CountUp, SpinningRecord } from '../components/Observatory'
import { PvPage, PvTop, PvHero, PvChips, PvPanel } from '../components/Premium'
import { errorMessage, getJson, getExample } from '../lib/api'

const ACCENT = '#5AC8FA'
const SUGGESTIONS = ['Mr. Brightside', 'Bohemian Rhapsody', 'HUMBLE.', 'Shape of You', 'Blinding Lights']

export default function SongPassport() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.track) { setQuery(s.track); search(s.track) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const data = (await getExample('song-passport-examples.json', q))
        || await getJson(`/api/song-passport/${encodeURIComponent(q)}`)
      setResult({
        title: data.title,
        artist: data.artist,
        playlists: data.playlist_count,
        pct: parseFloat((data.pct ?? 0).toFixed(2)),
        genres: data.genres || [],
        top_playlist_names: (data.top_playlist_names || []).map(s => s.trim()).filter(Boolean),
        listens: data.lb_listen_count,
        isrc: data.isrc,
        version_note: data.version_note,
      })
    } catch (e) {
      setResult({ title: q, artist: 'Unknown', playlists: 0, pct: 0, genres: [], top_playlist_names: [], _demo: true, _error: errorMessage(e) })
    } finally {
      setLoading(false)
    }
  }

  return (
    <PvPage>
      <PvTop sub="Song World" pill="Playlist travel" />
      <PvHero eyebrow="Track dossier" title={result?.title || 'Song Passport'}>
        Open a track biography — where it travels, which playlists claim it, and how far it reaches across the archive.
      </PvHero>

      <form className="pv-search" onSubmit={e => { e.preventDefault(); search(query) }}>
        <TrackAutocomplete value={query} onChange={setQuery} onSelect={item => { setQuery(item.title); search(item.title) }} placeholder="Track name…" />
        <button disabled={!query.trim() || loading}>{loading ? 'Working…' : 'Stamp passport'}</button>
      </form>
      <PvChips items={SUGGESTIONS} onPick={s => { setQuery(s); search(s) }} />

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/turntable.json" className="w-48 h-32 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Opening track passport…</p>
            </div>
          </div>
        )}

        {!result && !loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/vinyl-loading.json" className="w-36 h-36 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Search a track to stamp its playlist passport.</p>
            </div>
          </div>
        )}

        {result && !loading && (
          <div className="space-y-4">
            {result._demo && <p className="text-xs text-[var(--warning)]">Sample data — {result._error || 'live endpoint unavailable'}.</p>}
            <div className="grid grid-cols-1 xl:grid-cols-[300px_minmax(0,1fr)] gap-4 items-start">
              <PvPanel label="Track artifact" className="atlas-rise" style={{ '--i': 0 }}>
                <SpinningRecord label={result.title} sub={result.artist} accent={ACCENT} />
                {result.genres.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-5 justify-center">
                    {result.genres.slice(0, 6).map(g => (
                      <span key={g} className="text-[11px] px-2.5 py-1 rounded-full" style={{ color: ACCENT, background: `${ACCENT}18`, border: `1px solid ${ACCENT}44` }}>{g}</span>
                    ))}
                  </div>
                )}
              </PvPanel>

              <PvPanel label="Passport summary" className="atlas-rise" style={{ '--i': 1 }}>
                <p className="text-3xl sm:text-5xl font-extrabold tracking-[-0.04em] text-[var(--text-hi)]">{result.artist}</p>
                <p className="text-[var(--text-mid)] mt-4 leading-relaxed">
                  “{result.title}” appears in <span style={{ color: ACCENT }}><CountUp value={result.playlists} /></span> playlists — {result.pct}% of the full archive.
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-6">
                  <div className="pv-cell"><small>Playlists</small><strong>{result.playlists.toLocaleString()}</strong></div>
                  <div className="pv-cell"><small>Archive share</small><strong style={{ color: ACCENT }}>{result.pct}%</strong></div>
                  {result.listens != null && <div className="pv-cell"><small>Listens</small><strong>{Number(result.listens).toLocaleString()}</strong></div>}
                </div>
                {result.isrc && <p className="text-xs text-[var(--text-low)] mt-4 font-mono">ISRC {result.isrc}</p>}
                {result.version_note && <p className="text-xs text-[var(--text-low)] mt-2 leading-relaxed">{result.version_note}</p>}
              </PvPanel>
            </div>

            {result.top_playlist_names.length > 0 && (
              <PvPanel label="Playlist title evidence" className="atlas-rise" style={{ '--i': 2 }}>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6">
                  {result.top_playlist_names.slice(0, 12).map((name, i) => (
                    <p key={name + i} className="text-[var(--text-mid)] text-sm py-2 border-b border-[var(--hairline)]">
                      <span className="text-[var(--text-low)] mr-2 font-mono text-xs">{String(i + 1).padStart(2, '0')}</span>{name}
                    </p>
                  ))}
                </div>
              </PvPanel>
            )}
          </div>
        )}
      </div>
    </PvPage>
  )
}
