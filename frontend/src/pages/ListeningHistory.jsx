import { useCallback, useMemo, useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import RadialClock from '../components/listening/RadialClock'
import TasteStream from '../components/listening/TasteStream'
import YearSpiral from '../components/listening/YearSpiral'
import { getJson } from '../lib/api'
import {
  readHistoryFiles, summarize, tasteSeries, yearDays, yearsCovered,
  formatDuration, formatHour,
} from '../lib/listeningHistory'

const pct = v => `${(v * 100).toFixed(0)}%`

export default function ListeningHistory() {
  const [state, setState] = useState('idle')   // idle | reading | ready | error
  const [error, setError] = useState(null)
  const [summary, setSummary] = useState(null)
  const [format, setFormat] = useState(null)
  const [notes, setNotes] = useState([])
  const [year, setYear] = useState(null)
  const [corpus, setCorpus] = useState(null)
  const inputRef = useRef(null)

  const ingest = useCallback(async fileList => {
    if (!fileList?.length) return
    setState('reading'); setError(null); setCorpus(null)
    try {
      const { plays, format, skippedFiles } = await readHistoryFiles(fileList)
      if (!plays.length) {
        throw new Error('No streaming-history records were found in those files. Look for Streaming_History_Audio_*.json or StreamingHistory_music_*.json inside the export.')
      }
      const s = summarize(plays)
      setSummary(s); setFormat(format); setNotes(skippedFiles)
      const years = yearsCovered(s)
      setYear(years[years.length - 1])
      setState('ready')
      crossReference(s).then(setCorpus).catch(() => setCorpus({ error: true }))
    } catch (e) {
      setError(e.message || 'That file could not be read.')
      setState('error')
    }
  }, [])

  const onDrop = useCallback(e => {
    e.preventDefault()
    ingest(e.dataTransfer.files)
  }, [ingest])

  const years = summary ? yearsCovered(summary) : []
  const series = useMemo(() => (summary ? tasteSeries(summary, 8) : null), [summary])
  const days = useMemo(
    () => (summary && year ? yearDays(summary, year) : []), [summary, year])

  return (
    <PvPage>
      <PvTop sub="Your listening" pill="Personal history" />
      <PvHero eyebrow="Your own record" title="Listening History">
        Read your Spotify export against the atlas. Files stay in this browser and are never uploaded.
      </PvHero>

      <div className="max-w-6xl space-y-4">
        {state !== 'ready' && (
          <>
            <div
              className="listening-drop"
              onDragOver={e => e.preventDefault()}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              role="button" tabIndex={0}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click() }}
            >
              <Upload size={22} className="text-[var(--route-accent)]" />
              <p className="listening-drop-title">
                {state === 'reading' ? 'Reading your history…' : 'Drop your Spotify export here'}
              </p>
              <p className="listening-drop-sub">
                The <code>.json</code> files from your data download. Select them all at once.
              </p>
              <input
                ref={inputRef} type="file" accept=".json,application/json" multiple hidden
                onChange={e => ingest(e.target.files)}
              />
            </div>

            {error && <ErrorSignal detail={error} onRetry={() => setState('idle')}>We couldn’t read that export.</ErrorSignal>}

            <PvPanel label="How to get your file">
              <ol className="listening-steps">
                <li><strong>Spotify → Account → Privacy Settings.</strong> Scroll to “Download your data”.</li>
                <li><strong>Account data</strong> arrives in about five days and covers the past year. That is enough for everything on this page except exact track matching.</li>
                <li><strong>Extended streaming history</strong> can take up to 30 days and covers your whole account, with track IDs.</li>
                <li>Unzip it and drop the <code>.json</code> files above. Both formats are read automatically.</li>
              </ol>
              <p className="listening-privacy">
                Nothing is uploaded. The files are parsed in your browser and held in memory only
                until you close this tab — there is no account here and no server-side storage.
              </p>
            </PvPanel>
          </>
        )}

        {state === 'ready' && summary && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="pv-cell"><small>Listening time</small><strong>{formatDuration(summary.totals.totalMs)}</strong></div>
              <div className="pv-cell"><small>Tracks played</small><strong>{summary.totals.countedPlays.toLocaleString()}</strong></div>
              <div className="pv-cell"><small>Distinct artists</small><strong>{summary.totals.artists.toLocaleString()}</strong></div>
              <div className="pv-cell"><small>Days with listening</small><strong>{summary.totals.days.toLocaleString()}</strong></div>
            </div>

            <p className="atlas-coverage-note">
              {summary.range.from.toLocaleDateString()} – {summary.range.to.toLocaleDateString()} ·
              {format === 'basic'
                ? ' account-data export (past year, no track IDs)'
                : format === 'mixed' ? ' mixed export files' : ' extended streaming history'}
              {notes.length > 0 && ` · ${notes.length} file(s) ignored as unrecognised`}
            </p>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
              <PvPanel label="The shape of your day" className="atlas-rise" style={{ '--i': 0 }}>
                <RadialClock byHour={summary.byHour} byHourPlays={summary.byHourPlays} />
                <p className="listening-note">
                  Peak at {formatHour(summary.patterns.peak.hour)} on {summary.patterns.peak.bucket === 'weekend' ? 'weekends' : 'weekdays'}.
                </p>
              </PvPanel>

              <PvPanel label={`${year} day by day`} className="atlas-rise" style={{ '--i': 1 }}>
                {years.length > 1 && (
                  <div className="listening-years">
                    {years.map(y => (
                      <button key={y} type="button" onClick={() => setYear(y)}
                              className={y === year ? 'is-active' : undefined}>{y}</button>
                    ))}
                  </div>
                )}
                <YearSpiral days={days} year={year} />
              </PvPanel>
            </div>

            <PvPanel label="Taste drift" className="atlas-rise" style={{ '--i': 2 }}>
              <p className="listening-note listening-note-top">
                Your eight most-played artists, month by month. Bands swell while an artist held your
                attention and pinch to nothing when they lost it.
              </p>
              {series && <TasteStream series={series} />}
            </PvPanel>

            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-4 items-start">
              <PvPanel label="Most played" className="atlas-rise" style={{ '--i': 3 }}>
                <div className="listening-tops">
                  <TopList title="Artists" rows={summary.topArtists.slice(0, 10).map(a => ({ main: a.name, ms: a.ms, plays: a.plays }))} />
                  <TopList title="Tracks" rows={summary.topTracks.slice(0, 10).map(t => ({ main: t.track, sub: t.artist, ms: t.ms, plays: t.plays }))} />
                  {summary.topAlbums.length > 0 && (
                    <TopList title="Albums" rows={summary.topAlbums.slice(0, 10).map(a => ({ main: a.album, sub: a.artist, ms: a.ms, plays: a.plays }))} />
                  )}
                </div>
              </PvPanel>

              <PvPanel label="Listening patterns" className="atlas-rise atlas-sticky-aside" style={{ '--i': 4 }}>
                <dl className="listening-patterns">
                  <div><dt>Busiest day</dt><dd>{summary.patterns.busiestDay
                    ? `${summary.patterns.busiestDay[0]} · ${formatDuration(summary.patterns.busiestDay[1])}` : '—'}</dd></div>
                  <div><dt>Skip rate</dt><dd>{summary.patterns.skipRate == null
                    ? <span className="listening-unavailable">not in this export</span> : pct(summary.patterns.skipRate)}</dd></div>
                  <div><dt>Shuffle</dt><dd>{summary.patterns.shuffleRate == null
                    ? <span className="listening-unavailable">not in this export</span> : pct(summary.patterns.shuffleRate)}</dd></div>
                  <div><dt>Average per active day</dt><dd>{formatDuration(summary.totals.totalMs / Math.max(1, summary.totals.days))}</dd></div>
                  {summary.patterns.platforms.length > 0 && (
                    <div><dt>Top device</dt><dd>{summary.patterns.platforms[0][0]}</dd></div>
                  )}
                </dl>
              </PvPanel>
            </div>

            <PvPanel label="Your taste against the corpus" className="atlas-rise" style={{ '--i': 5 }}>
              <CorpusPanel corpus={corpus} />
            </PvPanel>

            <button type="button" className="listening-reset"
                    onClick={() => { setSummary(null); setState('idle'); setCorpus(null) }}>
              Load a different export
            </button>
          </>
        )}
      </div>
    </PvPage>
  )
}

function TopList({ title, rows }) {
  const max = Math.max(...rows.map(r => r.ms), 1)
  return (
    <div>
      <h3 className="listening-top-title">{title}</h3>
      <ol className="listening-top-list">
        {rows.map((r, i) => (
          <li key={`${r.main}-${r.sub || ''}`}>
            <span className="listening-top-rank">{String(i + 1).padStart(2, '0')}</span>
            <span className="listening-top-main">
              <b>{r.main}</b>{r.sub && <em>{r.sub}</em>}
            </span>
            <span className="listening-top-bar"><i style={{ width: `${(r.ms / max) * 100}%` }} /></span>
            <span className="listening-top-ms">{formatDuration(r.ms)}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

// The part only this project can do: place the artists you actually played
// against how far they travel in the 1M-playlist corpus.
//
// A 404 means the artist genuinely isn't in the corpus table. Anything else
// (backend down, timeout, 5xx) means we don't know — and must not be reported
// as absence, which would state a fact about the data from a transport failure.
async function crossReference(summary) {
  const names = summary.topArtists.slice(0, 8).map(a => a.name)
  const results = await Promise.all(names.map(async name => {
    try {
      const d = await getJson(`/api/artist-ubiquity/${encodeURIComponent(name)}`, { timeoutMs: 20000 })
      return { name, state: 'found', playlistCount: d.playlist_count, pct: d.pct, rank: d.rank }
    } catch (e) {
      return { name, state: e?.status === 404 ? 'absent' : 'unavailable' }
    }
  }))
  const found = results.filter(r => r.state === 'found')
  const unavailable = results.filter(r => r.state === 'unavailable').length
  const avgPct = found.length ? found.reduce((a, b) => a + b.pct, 0) / found.length : null
  return {
    results, avgPct,
    matched: found.length,
    total: names.length,
    unavailable,
    // Every lookup failing for transport reasons is an outage, not a finding.
    offline: unavailable === names.length,
  }
}

function CorpusPanel({ corpus }) {
  if (!corpus) return <p className="listening-note">Measuring your artists against the corpus…</p>
  if (corpus.error || corpus.offline) {
    return (
      <p className="listening-note">
        The corpus lookup is unavailable right now, so these artists could not be placed. This is a
        connection problem, not a statement about whether they appear in the corpus.
      </p>
    )
  }

  const max = Math.max(...corpus.results.filter(r => r.state === 'found').map(r => r.pct), 1)
  return (
    <>
      <p className="listening-note listening-note-top">
        How far your most-played artists travel across the million-playlist corpus. This measures
        placement, not listening: a high bar means many people filed them into playlists, not that
        many people played them. The corpus is a fixed archive of playlists built up to 2017, so an
        artist who broke out after that ranks low here however popular they are now — a low bar can
        mean “arrived late”, not “obscure”.
      </p>
      <ul className="listening-corpus">
        {corpus.results.map(r => (
          <li key={r.name}>
            <span className="listening-corpus-name">{r.name}</span>
            {r.state === 'found' ? (
              <>
                <span className="listening-corpus-bar"><i style={{ width: `${(r.pct / max) * 100}%` }} /></span>
                <span className="listening-corpus-val">{r.pct.toFixed(2)}% of playlists · #{r.rank}</span>
              </>
            ) : (
              <span className="listening-corpus-missing">
                {r.state === 'absent' ? 'outside the top-artist table' : 'lookup unavailable'}
              </span>
            )}
          </li>
        ))}
      </ul>
      {corpus.avgPct != null && (
        <p className="listening-verdict">
          Your top artists sit in <strong>{corpus.avgPct.toFixed(2)}%</strong> of playlists on average
          {corpus.matched < corpus.total && ` (${corpus.matched} of ${corpus.total} placed`}
          {corpus.matched < corpus.total && corpus.unavailable > 0 && `, ${corpus.unavailable} unavailable`}
          {corpus.matched < corpus.total && ')'}.
        </p>
      )}
    </>
  )
}
