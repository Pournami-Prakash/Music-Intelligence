import { useState, useEffect } from 'react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'

const ACCENT = '#94A3B8'
const SORTS = ['Recently removed', 'Longest run']

export default function EditorialGraveyard() {
  const [data, setData] = useState(null)
  const [sort, setSort] = useState('Recently removed')
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    fetch('/api/editorial-graveyard')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.tracks) { setData(d); setSelected(d.tracks[0]) } })
      .catch(() => {})
  }, [])

  if (!data) {
    return (
      <PvPage>
        <PvTop sub="Drop Archive" pill="Editorial afterlife" />
        <PvHero eyebrow="Removed-track ledger" title="Editorial Graveyard">
          Browse the tracks that entered Spotify editorial playlists, stayed a while, then vanished from the official shelf.
        </PvHero>
        <div className="pv-panel max-w-6xl grid place-items-center" style={{ minHeight: 340 }}>
          <div className="text-center"><LottiePlayer src="/assets/no-data.json" className="w-40 h-40 mx-auto" /><p className="mt-2 text-[var(--text-mid)]">Opening the removal ledger…</p></div>
        </div>
      </PvPage>
    )
  }

  const tracks = [...data.tracks].sort((a, b) =>
    sort === 'Longest run' ? b.days - a.days : new Date(b.removed) - new Date(a.removed)
  )
  const avgDays = Math.round(data.tracks.reduce((s, t) => s + (t.days || 0), 0) / data.tracks.length)
  const maxDays = Math.max(...data.tracks.map(t => t.days || 0), 1)

  return (
    <PvPage>
      <PvTop sub="Drop Archive" pill="Editorial afterlife" />
      <PvHero eyebrow="Removed-track ledger" title="Editorial Graveyard">
        Browse the tracks that entered Spotify editorial playlists, stayed a while, then vanished from the official shelf.
      </PvHero>

      <div className="max-w-6xl grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)] gap-4 items-start">
        <div className="space-y-4">
          <PvPanel label="Archive summary" className="atlas-rise" style={{ '--i': 0 }}>
            <p className="text-5xl font-extrabold tracking-[-0.04em]" style={{ color: ACCENT }}>{(data.total_removed / 1e6).toFixed(2)}M</p>
            <p className="text-[var(--text-low)] text-xs uppercase tracking-[0.14em] mt-1">total removals</p>
            <div className="grid grid-cols-2 gap-3 mt-4">
              <div className="pv-cell"><small>Avg run</small><strong>{avgDays}d</strong></div>
              <div className="pv-cell"><small>Sample</small><strong>{data.tracks.length}</strong></div>
            </div>
          </PvPanel>

          {selected && (
            <PvPanel label="Selected file" className="atlas-rise" style={{ '--i': 1 }}>
              <p className="text-xl font-bold text-[var(--text-hi)]">{selected.title}</p>
              <p className="text-[var(--text-mid)] text-sm mt-1">{selected.artist}</p>
              <div className="mt-3">
                <div className="flex justify-between text-sm mb-1.5"><span className="text-[var(--text-mid)]">run length</span><span style={{ color: ACCENT }}>{selected.days}d</span></div>
                <div className="h-1.5 rounded-full bg-white/10 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${(selected.days / maxDays) * 100}%`, background: ACCENT }} /></div>
              </div>
              <p className="text-[var(--text-low)] text-xs mt-4 leading-relaxed">In <span className="text-[var(--text-mid)]">{selected.playlist}</span> from {selected.added} to {selected.removed}.</p>
            </PvPanel>
          )}
        </div>

        <PvPanel
          label="Removal ledger"
          className="atlas-rise"
          style={{ '--i': 2 }}
          action={
            <div className="flex gap-2">
              {SORTS.map(o => (
                <button key={o} onClick={() => setSort(o)} className="px-3 py-1 rounded-full text-xs border transition-colors"
                  style={{ borderColor: sort === o ? ACCENT : 'var(--hairline)', color: sort === o ? ACCENT : 'var(--text-low)', background: sort === o ? `${ACCENT}22` : 'transparent' }}>
                  {o}
                </button>
              ))}
            </div>
          }
        >
          <div className="space-y-px max-h-[560px] overflow-y-auto no-scrollbar">
            {tracks.map((t, i) => (
              <button
                key={`${t.title}-${t.playlist}-${i}`}
                onClick={() => setSelected(t)}
                className="w-full grid grid-cols-[auto_minmax(0,1fr)_auto_auto] gap-4 items-center py-2.5 px-2 rounded-lg text-left border-b border-[var(--hairline)] last:border-0 hover:bg-white/[0.04]"
                style={selected === t ? { background: 'rgba(255,255,255,0.05)' } : undefined}
              >
                <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                <span className="min-w-0">
                  <span className="block text-sm text-[var(--text-hi)] truncate">{t.title}</span>
                  <span className="block text-xs text-[var(--text-low)] truncate">{t.artist} · {t.playlist}</span>
                </span>
                <span className="text-xs text-[var(--text-mid)]">{t.days}d</span>
                <span className="text-xs text-[var(--text-low)] w-20 text-right">{t.removed}</span>
              </button>
            ))}
          </div>
        </PvPanel>
      </div>
    </PvPage>
  )
}
