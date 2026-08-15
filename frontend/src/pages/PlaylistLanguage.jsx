import { useEffect, useState } from 'react'
import { Link2 } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson, readSharedParam, replaceSharedParams } from '../lib/api'

const CAT_COLORS = { mood: '#FF7A9C', activity: '#3DDC97', time: '#5AC8FA', identity: '#B08CF8', genre: '#F5C451' }

export default function PlaylistLanguage() {
  const [url, setUrl] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [corpus, setCorpus] = useState(null)

  const analyze = async (targetUrl = url) => {
    if (!targetUrl.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await getJson('/api/playlist-profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ playlist_url: targetUrl.trim() }),
      })
      setResult(data)
      replaceSharedParams({ playlist: targetUrl.trim() })
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const sharedPlaylist = readSharedParam('playlist')
    if (sharedPlaylist) {
      setUrl(sharedPlaylist)
      analyze(sharedPlaylist)
    }
  }, [])

  // Corpus-wide title vocabulary (frontend/public/data/playlist-language.json),
  // the same snapshot /api/playlist-language serves. It fills the pre-input
  // state so the room's "vocabulary of 1M playlist names" promise is on-page.
  useEffect(() => {
    let cancelled = false
    fetch('/data/playlist-language.json')
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (!cancelled && d?.words?.length) setCorpus(d) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  return (
    <PvPage>
      <PvTop sub="Vibe Dictionary" pill="Playlist profile" />
      <PvHero eyebrow="Playlist evidence" title={result?.playlist?.name || 'Playlist Language'}>
        Paste a public Spotify playlist to inspect its title vocabulary, artist concentration, and track makeup against the million-playlist corpus.
      </PvHero>

      <div className="max-w-6xl space-y-4">
        <form className="pv-search" onSubmit={e => { e.preventDefault(); analyze() }}>
          <div className="flex min-w-0 flex-1 items-center gap-3 px-4">
            <Link2 size={17} className="shrink-0 text-[var(--text-low)]" />
            <input
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://open.spotify.com/playlist/…"
              maxLength={2048}
              aria-label="Public Spotify playlist link"
              className="min-w-0 flex-1 bg-transparent text-[var(--text-hi)] outline-none placeholder:text-[var(--text-low)]"
            />
          </div>
          <button disabled={!url.trim() || loading}>{loading ? 'Reading…' : 'Read playlist'}</button>
        </form>

        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 260 }}>
            <div className="text-center"><LottiePlayer src="/assets/formula-pulse.json" className="w-36 h-36 mx-auto" /><p className="mt-2 text-[var(--text-mid)]">Importing tracks and profiling the playlist…</p></div>
          </div>
        )}

        {error && !loading && (
          <ErrorSignal detail={error} onRetry={() => analyze()}>
            We couldn’t read this playlist.
          </ErrorSignal>
        )}

        {!result && !loading && !error && (
          <>
            <div className="pv-panel py-10 text-center">
              <p className="text-[var(--text-hi)] font-semibold">Start with a playlist, not sample data.</p>
              <p className="mt-2 text-sm text-[var(--text-mid)]">Public Spotify playlists work without signing in.</p>
            </div>

            {corpus && (
              <PvPanel label="Corpus vocabulary" className="atlas-rise" style={{ '--i': 0 }}>
                <p className="mb-4 text-sm text-[var(--text-mid)]">
                  The {corpus.words.length} most common words across {corpus.total_playlists.toLocaleString()} playlist
                  titles. Each percentage is the share of titles containing that word.
                </p>
                <div className="flex flex-wrap gap-2">
                  {corpus.words.map(w => (
                    <span
                      key={w.word}
                      className="inline-flex items-baseline gap-2 rounded-full border px-3 py-1.5 text-sm"
                      style={{
                        borderColor: CAT_COLORS[w.cat] || 'var(--hairline)',
                        color: CAT_COLORS[w.cat] || 'var(--text-mid)',
                        background: 'rgba(255,255,255,0.03)',
                      }}
                    >
                      {w.word}
                      <span className="font-mono text-[11px] text-[var(--text-low)]">{w.pct}%</span>
                    </span>
                  ))}
                </div>
              </PvPanel>
            )}
          </>
        )}

        {result && !loading && !error && (
          <>
            {result.playlist.import_mode === 'public_embed_preview' && (
              <p className="atlas-coverage-note">Spotify exposed a public {result.playlist.track_count}-track preview. These results describe that visible sample, not any hidden remainder.</p>
            )}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="pv-cell"><small>Tracks read</small><strong>{result.playlist.track_count}</strong></div>
              <div className="pv-cell"><small>Distinct top artists</small><strong>{result.top_artists.length}</strong></div>
              <div className="pv-cell"><small>Owner</small><strong className="truncate">{result.playlist.owner || '—'}</strong></div>
              <div className="pv-cell"><small>Followers</small><strong>{result.playlist.followers?.toLocaleString?.() ?? '—'}</strong></div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-4 items-start">
              <PvPanel label="Artist concentration" className="atlas-rise" style={{ '--i': 0 }}>
                <div className="space-y-4">
                  {result.top_artists.map((item, i) => (
                    <div key={item.artist}>
                      <div className="mb-1.5 flex items-baseline justify-between gap-4">
                        <span className="text-sm text-[var(--text-hi)]"><span className="mr-2 font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>{item.artist}</span>
                        <span className="text-xs text-[var(--text-mid)]">{item.tracks} tracks · {item.pct}%</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                        <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${Math.max(item.pct, 1)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </PvPanel>

              <PvPanel label="Title vocabulary" className="atlas-rise" style={{ '--i': 1 }}>
                {result.title_terms.length ? result.title_terms.map(term => (
                  <div key={term.word} className="border-b border-[var(--hairline)] py-3 first:pt-0 last:border-0">
                    <div className="flex items-center justify-between gap-4">
                      <strong className="text-lg" style={{ color: CAT_COLORS[term.theme] || 'var(--text-hi)' }}>{term.word}</strong>
                      <span className="text-xs uppercase tracking-wider text-[var(--text-low)]">{term.theme || 'rare / unclassified'}</span>
                    </div>
                    <p className="mt-1 text-xs text-[var(--text-mid)]">
                      {term.known ? `${term.count.toLocaleString()} playlist titles in the corpus` : 'No strong corpus match'}
                    </p>
                  </div>
                )) : <p className="text-sm text-[var(--text-mid)]">The playlist title contains no analyzable words.</p>}
              </PvPanel>
            </div>

            <PvPanel label="Imported track evidence" className="atlas-rise" style={{ '--i': 2 }}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
                {result.tracks.map((track, i) => (
                  <div key={track.uri || `${track.name}-${i}`} className="flex items-baseline gap-3 border-b border-[var(--hairline)] py-3">
                    <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                    <p className="min-w-0 text-sm text-[var(--text-hi)]"><span className="font-semibold">{track.name}</span><span className="text-[var(--text-mid)]"> — {track.artist}</span></p>
                  </div>
                ))}
              </div>
            </PvPanel>
          </>
        )}
      </div>
    </PvPage>
  )
}
