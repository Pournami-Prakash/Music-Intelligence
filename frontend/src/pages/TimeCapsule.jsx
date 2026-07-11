import { useState, useEffect } from 'react'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { apiUrl } from '../lib/api'

const ACCENT = '#94A3B8'
const ERAS = ['1960s', '1970s', '1980s', '1990s', '2000s', '2010s', '2020s']

export default function TimeCapsule() {
  const [era, setEra] = useState('2010s')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = (e) => {
    setLoading(true)
    setData(null)
    fetch(apiUrl(`/api/time-capsule?era=${encodeURIComponent(e)}&limit=20`))
      .then(r => r.ok ? r.json() : null)
      .then(d => setData(d))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load('2010s') }, [])
  const pick = (e) => { setEra(e); load(e) }

  const maxYear = data?.year_distribution?.length ? Math.max(...data.year_distribution.map(y => y.count)) : 1

  return (
    <PvPage>
      <PvTop sub="Drop Archive" pill="Cultural capsule" />
      <PvHero eyebrow="Archive capsule" title={data ? `The ${data.era}` : 'Time Capsule'}>
        Open an era and see the songs, artists, and chart moments that defined it in playlist culture.
      </PvHero>

      <div className="max-w-6xl">
        <div className="flex flex-wrap gap-2 mb-4">
          {ERAS.map(e => (
            <button
              key={e}
              onClick={() => pick(e)}
              className="px-4 py-2 rounded-full text-sm border transition-colors"
              style={{
                borderColor: era === e ? ACCENT : 'var(--hairline)',
                background: era === e ? `${ACCENT}22` : 'rgba(255,255,255,0.03)',
                color: era === e ? '#cbd5e1' : 'var(--text-mid)',
              }}
            >
              {e}
            </button>
          ))}
        </div>

        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 320 }}>
            <div className="text-center"><LottiePlayer src="/assets/loading-cubes.json" className="w-32 h-32 mx-auto" /><p className="mt-2 text-[var(--text-mid)]">Opening the {era} capsule…</p></div>
          </div>
        )}

        {data && !loading && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 xl:grid-cols-[300px_minmax(0,1fr)] gap-4 items-start">
              <PvPanel label="Capsule artifact" className="atlas-rise" style={{ '--i': 0 }}>
                <p className="text-6xl font-extrabold tracking-[-0.04em] text-[var(--text-hi)]">{data.era}</p>
                <div className="grid grid-cols-2 gap-3 mt-4">
                  <div className="pv-cell"><small>Tracks</small><strong><CountUp value={data.track_count} /></strong></div>
                  <div className="pv-cell"><small>Source</small><strong className="capitalize text-base">{data.data_source}</strong></div>
                </div>
                {data.date_range && <p className="text-[var(--text-low)] text-xs mt-3">{data.date_range.min} → {data.date_range.max}</p>}
              </PvPanel>

              <PvPanel label="Year distribution" className="atlas-rise" style={{ '--i': 1 }}>
                <div className="flex items-end gap-1.5" style={{ height: 160 }}>
                  {(data.year_distribution || []).map(y => (
                    <div key={y.year} className="flex-1 flex flex-col items-center justify-end group" title={`${y.year}: ${y.count.toLocaleString()}`}>
                      <div className="w-full rounded-t" style={{ height: `${Math.max(2, (y.count / maxYear) * 100)}%`, background: ACCENT, opacity: 0.8 }} />
                      <span className="text-[9px] text-[var(--text-low)] mt-1 rotate-0">{String(y.year).slice(2)}</span>
                    </div>
                  ))}
                </div>
              </PvPanel>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <PvPanel label="Defining tracks" className="atlas-rise" style={{ '--i': 2 }}>
                {(data.top_tracks || []).slice(0, 8).map((t, i) => (
                  <div key={t.title + i} className="flex items-baseline gap-3 py-1.5 border-b border-[var(--hairline)] last:border-0">
                    <span className="font-mono text-xs text-[var(--text-low)]">{String(i + 1).padStart(2, '0')}</span>
                    <div className="min-w-0">
                      <p className="text-[var(--text-hi)] text-sm truncate">{t.title}</p>
                      <p className="text-[var(--text-low)] text-xs truncate">{t.artist} · {t.appearances}×</p>
                    </div>
                  </div>
                ))}
              </PvPanel>

              <PvPanel label="Artists of this era" className="atlas-rise" style={{ '--i': 3 }}>
                {(data.top_artists || []).slice(0, 8).map((a, i) => (
                  <div key={a.name + i} className="flex justify-between items-baseline py-1.5 border-b border-[var(--hairline)] last:border-0">
                    <span className="text-[var(--text-hi)] text-sm truncate">{a.name}</span>
                    <span className="text-[var(--text-low)] text-xs shrink-0 ml-2">{a.track_appearances}×</span>
                  </div>
                ))}
              </PvPanel>

              <PvPanel label="Chart #1s" className="atlas-rise" style={{ '--i': 4 }}>
                {(data.chart_number_ones || []).slice(0, 8).map((c, i) => (
                  <div key={c.title + i} className="py-1.5 border-b border-[var(--hairline)] last:border-0">
                    <p className="text-[var(--text-hi)] text-sm truncate">{c.title}</p>
                    <p className="text-[var(--text-low)] text-xs truncate">{c.artist}{c.total_weeks ? ` · ${c.total_weeks}w` : ''}</p>
                  </div>
                ))}
                {(!data.chart_number_ones || data.chart_number_ones.length === 0) && <p className="text-[var(--text-low)] text-sm">No chart #1s recorded for this era.</p>}
              </PvPanel>
            </div>
          </div>
        )}
      </div>
    </PvPage>
  )
}
