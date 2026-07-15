import { useState, useEffect } from 'react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'

export default function MoodMap() {
  const [clusters, setClusters] = useState(null)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    fetch('/data/mood-map.json')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.clusters) { setClusters(d.clusters); setSelected(d.clusters[0]) } })
      .catch(() => {})
  }, [])

  if (!clusters) {
    return (
      <PvPage>
        <PvTop sub="Deep Map" pill="1M titles" />
        <PvHero eyebrow="Cultural mood field" title="Mood Map">
          Cluster playlist-title language into emotional territories and inspect the phrases that shape each region.
        </PvHero>
        <div className="pv-panel max-w-6xl grid place-items-center" style={{ minHeight: 360 }}>
          <div className="text-center">
            <LottiePlayer src="/assets/radar.json" className="w-44 h-44 mx-auto" />
            <p className="mt-2 text-[var(--text-mid)]">Mapping mood territories…</p>
          </div>
        </div>
      </PvPage>
    )
  }

  const n = clusters.length
  const maxPct = Math.max(...clusters.map(c => c.pct), 1)

  return (
    <PvPage>
      <PvTop sub="Deep Map" pill="1M titles" />
      <PvHero eyebrow="Cultural mood field" title="Mood Map">
        Cluster playlist-title language into emotional territories and inspect the phrases that shape each region.
      </PvHero>

      <div className="max-w-6xl grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_330px] gap-4 items-start">
        <PvPanel label="Mood territories" className="atlas-rise" style={{ '--i': 0 }}>
          <div className="relative rounded-2xl bg-black/25 border border-[var(--hairline)] overflow-hidden" style={{ minHeight: 520 }}>
            {clusters.map((c, i) => {
              const angle = (i / n) * 2 * Math.PI - Math.PI / 2
              const left = 50 + Math.cos(angle) * 33
              const top = 50 + Math.sin(angle) * 30
              const size = 60 + (c.pct / maxPct) * 74
              const isSel = selected?.id === c.id
              return (
                <button
                  key={c.id}
                  onClick={() => setSelected(c)}
                  className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full grid place-items-center text-center transition-transform hover:scale-105"
                  style={{
                    left: `${left}%`, top: `${top}%`, width: size, height: size,
                    background: `radial-gradient(circle at 40% 35%, ${c.color}66, ${c.color}18 60%, transparent 75%)`,
                    border: `1px solid ${c.color}${isSel ? 'cc' : '55'}`,
                    boxShadow: isSel ? `0 0 32px ${c.color}66` : 'none',
                  }}
                >
                  <span className="text-[11px] font-semibold px-1 leading-tight" style={{ color: c.color }}>{c.label}</span>
                </button>
              )
            })}
          </div>
        </PvPanel>

        <div className="space-y-4">
          <PvPanel label="Territory density" className="atlas-rise" style={{ '--i': 1 }}>
            {clusters.map(c => (
              <button key={c.id} onClick={() => setSelected(c)} className="w-full text-left mb-3 last:mb-0">
                <div className="flex justify-between text-sm mb-1.5">
                  <span className="text-[var(--text-mid)]">{c.label}</span>
                  <span style={{ color: c.color }}>{c.pct}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${(c.pct / maxPct) * 100}%`, background: c.color }} />
                </div>
              </button>
            ))}
          </PvPanel>

          {selected && (
            <PvPanel label="Selected territory" className="atlas-rise" style={{ '--i': 2 }}>
              <p className="text-xl font-bold" style={{ color: selected.color }}>{selected.label}</p>
              <p className="text-[var(--text-mid)] text-sm mt-2">{selected.description}</p>
              <p className="text-[var(--text-low)] text-xs mt-3">{selected.count.toLocaleString()} playlists · {selected.pct}%</p>
              <div className="flex flex-wrap gap-2 mt-3">
                {(selected.top_terms || []).slice(0, 8).map(t => (
                  <span key={t} className="text-xs px-2.5 py-1 rounded-full text-[var(--text-mid)] border border-[var(--hairline)]">{t}</span>
                ))}
              </div>
            </PvPanel>
          )}
        </div>
      </div>
    </PvPage>
  )
}
