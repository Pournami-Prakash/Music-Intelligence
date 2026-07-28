import { useEffect, useState } from 'react'
import { Fingerprint, Link2 } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { errorMessage, getJson, readSharedParam, replaceSharedParams } from '../lib/api'

export default function PlaylistForensics() {
  const [url, setUrl] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const analyze = async (targetUrl = url) => {
    if (!targetUrl.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await getJson('/api/forensics', {
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

  const outside = result ? Math.round(result.outside_reference_pct ?? result.organic_pct) : 0
  const editorial = result ? Math.round(result.editorial_pct) : 0
  const verdictColor = editorial < 40 ? '#3DDC97' : '#FF7A9C'

  return (
    <PvPage>
      <PvTop sub="Deep Map" pill="Reference comparison" />
      <PvHero eyebrow="Editorial reference" title="Editorial Overlap">
        Paste a public Spotify playlist link. The atlas imports its tracks and measures how much of the selection appears in Spotify editorial playlists.
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
          <button disabled={!url.trim() || loading}>
            <Fingerprint size={15} /> {loading ? 'Importing…' : 'Inspect playlist'}
          </button>
        </form>

        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 240 }}>
            <div className="text-center"><LottiePlayer src="/assets/formula-pulse.json" className="w-36 h-36 mx-auto" /><p className="mt-2 text-[var(--text-mid)]">Importing the playlist and checking editorial overlap…</p></div>
          </div>
        )}

        {error && !loading && (
          <ErrorSignal detail={error} onRetry={() => analyze()}>
            We couldn’t inspect this playlist.
          </ErrorSignal>
        )}

        {result && !loading && !error && (
          <>
            <p className="atlas-coverage-note">
              {result.playlist_name ? `Analysing “${result.playlist_name}”. ` : ''}
              This score measures track overlap with Spotify editorial playlists; it does not identify who personally curated the playlist.
            </p>
            <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
              <div className="pv-panel atlas-rise" style={{ '--i': 0 }}>
                <p className="pv-panel-label">Editorial overlap</p>
                <p className="text-2xl font-bold capitalize" style={{ color: verdictColor }}>{String(result.verdict || '').replace(/_/g, ' ')}</p>
                <div className="mt-5 space-y-3">
                  <div>
                    <div className="flex justify-between text-sm mb-1.5"><span className="text-[var(--text-mid)]">not observed in reference set</span><span style={{ color: '#3DDC97' }}>{outside}%</span></div>
                    <div className="h-1.5 rounded-full bg-white/10 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${outside}%`, background: '#3DDC97' }} /></div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-1.5"><span className="text-[var(--text-mid)]">editorial overlap</span><span style={{ color: '#FF7A9C' }}>{editorial}%</span></div>
                    <div className="h-1.5 rounded-full bg-white/10 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${editorial}%`, background: '#FF7A9C' }} /></div>
                  </div>
                </div>
              </div>

              <div className="pv-panel atlas-rise" style={{ '--i': 1 }}>
                <p className="pv-panel-label">Evidence</p>
                <p className="text-[var(--text-mid)] leading-relaxed">{result.verdict_detail}</p>
                {result.signals?.length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
                    {result.signals.map(s => (
                      <div key={s.label} className="pv-cell">
                        <small>{s.label}</small>
                        <strong>{String(s.value)}</strong>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </PvPage>
  )
}
