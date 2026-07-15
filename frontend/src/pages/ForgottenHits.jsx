import { useState, useEffect } from 'react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'

const ACCENT = '#94A3B8'
const SORTS = [['days_on', 'Longest run'], ['removed', 'Recently dropped'], ['chart_peak', 'Chart peak']]

export default function ForgottenHits() {
  const [data, setData] = useState(null)
  const [sort, setSort] = useState('days_on')
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    fetch('/data/forgotten-hits.json')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.tracks) { setData(d); setSelected(d.tracks[0]) } })
      .catch(() => {})
  }, [])

  if (!data) {
    return (
      <PvPage>
        <PvTop sub="Drop Archive" pill="Forgotten hits" />
        <PvHero eyebrow="Long-run ledger" title="Forgotten Hits">
          Songs that lived on editorial playlists for years, then quietly left — long runs, faded signal.
        </PvHero>
        <div className="pv-panel max-w-6xl grid place-items-center" style={{ minHeight: 340 }}>
          <div className="text-center"><LottiePlayer src="/assets/no-data.json" className="w-40 h-40 mx-auto" /><p className="mt-2 text-[var(--text-mid)]">Loading decay records…</p></div>
        </div>
      </PvPage>
    )
  }

  const tracks = [...data.tracks].sort((a, b) => {
    if (sort === 'removed') return new Date(b.removed) - new Date(a.removed)
    if (sort === 'chart_peak') return (a.chart_peak || 999) - (b.chart_peak || 999)
    return (b.days_on || 0) - (a.days_on || 0)
  })

  return (
    <PvPage>
      <PvTop sub="Drop Archive" pill="Forgotten hits" />
      <PvHero eyebrow="Long-run ledger" title="Forgotten Hits">
        Songs that lived on editorial playlists for years, then quietly left — long runs, faded signal.
      </PvHero>

      <div className="max-w-6xl grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
        <div className="space-y-4">
          <PvPanel label="Archive summary" className="atlas-rise" style={{ '--i': 0 }}>
            <p className="text-5xl font-extrabold tracking-[-0.04em]" style={{ color: ACCENT }}>{(data.total / 1000).toFixed(0)}k</p>
            <p className="text-[var(--text-low)] text-xs uppercase tracking-[0.14em] mt-1">forgotten records</p>
          </PvPanel>

          {selected && (
            <PvPanel label="Selected record" className="atlas-rise" style={{ '--i': 1 }}>
              <p className="text-xl font-bold text-[var(--text-hi)]">{selected.title}</p>
              <p className="text-[var(--text-mid)] text-sm mt-1">{selected.artist}</p>
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div className="pv-cell"><small>Run</small><strong>{(selected.days_on / 365).toFixed(1)}y</strong></div>
                <div className="pv-cell"><small>Chart peak</small><strong>{selected.chart_peak ? `#${selected.chart_peak}` : '—'}</strong></div>
              </div>
              <p className="text-[var(--text-low)] text-xs mt-4 leading-relaxed">In <span className="text-[var(--text-mid)]">{selected.playlist}</span> · dropped {selected.removed}.</p>
            </PvPanel>
          )}
        </div>

        <PvPanel
          label="Decay ledger"
          className="atlas-rise"
          style={{ '--i': 2 }}
          action={
            <div className="flex flex-wrap gap-2">
              {SORTS.map(([key, lbl]) => (
                <button key={key} onClick={() => setSort(key)} className="px-3 py-1 rounded-full text-xs border transition-colors"
                  style={{ borderColor: sort === key ? ACCENT : 'var(--hairline)', color: sort === key ? ACCENT : 'var(--text-low)', background: sort === key ? `${ACCENT}22` : 'transparent' }}>
                  {lbl}
                </button>
              ))}
            </div>
          }
        >
          <div className="space-y-px max-h-[560px] overflow-y-auto no-scrollbar">
            {tracks.map((t, i) => (
              <button
                key={`${t.title}-${i}`}
                onClick={() => setSelected(t)}
                className="w-full grid grid-cols-[auto_minmax(0,1fr)_auto_auto] gap-4 items-center py-2.5 px-2 rounded-lg text-left border-b border-[var(--hairline)] last:border-0 hover:bg-white/[0.04]"
                style={selected === t ? { background: 'rgba(255,255,255,0.05)' } : undefined}
              >
                <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                <span className="min-w-0">
                  <span className="block text-sm text-[var(--text-hi)] truncate">{t.title}</span>
                  <span className="block text-xs text-[var(--text-low)] truncate">{t.artist} · {t.playlist}</span>
                </span>
                <span className="text-xs text-[var(--text-mid)] w-12 text-right">{(t.days_on / 365).toFixed(1)}y</span>
                <span className="text-xs text-[var(--text-low)] w-12 text-right">{t.chart_peak ? `#${t.chart_peak}` : '—'}</span>
              </button>
            ))}
          </div>
        </PvPanel>
      </div>
    </PvPage>
  )
}
