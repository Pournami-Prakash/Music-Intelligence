import { useState, useEffect } from 'react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { ErrorSignal } from '../components/SignalState'
import { readSharedParam, replaceSharedParams } from '../lib/api'

export default function MoodMap() {
  const [clusters, setClusters] = useState(null)
  const [selected, setSelected] = useState(null)
  const [meta, setMeta] = useState(null)
  const [error, setError] = useState(false)

  const load = () => {
    setError(false)
    fetch('/data/mood-map.json')
      .then(r => {
        if (!r.ok) throw new Error('snapshot_unavailable')
        return r.json()
      })
      .then(d => {
        if (d?.clusters) {
          const sharedMood = readSharedParam('mood')
          setClusters(d.clusters)
          setSelected(d.clusters.find(cluster => cluster.id === sharedMood) || d.clusters[0])
          setMeta(d)
        } else throw new Error('snapshot_empty')
      })
      .catch(() => setError(true))
  }

  useEffect(() => { load() }, [])

  if (!clusters) {
    return (
      <PvPage>
        <PvTop sub="Deep Map" pill="1M titles" />
        <PvHero eyebrow="Cultural mood field" title="Mood Map">
          Cluster the language of a million playlist titles from 2010 to 2017 into emotional
          territories, and inspect the phrases that shape each region.
        </PvHero>
        {error ? (
          <div className="max-w-6xl">
            <ErrorSignal detail="The Mood Map snapshot could not be loaded." onRetry={load}>
              The title territories are temporarily unavailable.
            </ErrorSignal>
          </div>
        ) : (
          <div className="pv-panel max-w-6xl grid place-items-center" style={{ minHeight: 360 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/radar.json" className="w-44 h-44 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Mapping mood territories…</p>
            </div>
          </div>
        )}
      </PvPage>
    )
  }

  const totalPlaylists = meta?.total_playlists || 1_000_000
  const assignmentCount = meta?.assignment_count || clusters.reduce((sum, cluster) => sum + cluster.count, 0)
  const matchedCount = meta?.unique_matched_titles ?? assignmentCount
  const matchedPct = matchedCount / totalPlaylists * 100
  const scaleMax = Math.ceil(Math.max(...clusters.map(cluster => cluster.pct)))

  return (
    <PvPage>
      <PvTop sub="Deep Map" pill="1M titles" />
      <PvHero eyebrow="Playlist-title evidence" title="Mood Map">
        Which moods and occasions people named explicitly in a million playlist titles, 2010–2017.
      </PvHero>

      <div className="max-w-6xl grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_330px] gap-4 items-start">
        <PvPanel label="Evidence index" className="atlas-rise" style={{ '--i': 0 }}>
          <div className="mood-coverage grid grid-cols-3 border-y border-[var(--hairline)] mb-6">
            <div className="py-4 pr-3">
              <b className="block text-2xl text-[var(--text-hi)]">{matchedPct.toFixed(2)}%</b>
              <small className="text-[10px] text-[var(--text-low)] uppercase tracking-wider">corpus coverage</small>
            </div>
            <div className="py-4 px-3 border-x border-[var(--hairline)]">
              <b className="block text-2xl text-[var(--text-hi)]">{matchedCount.toLocaleString()}</b>
              <small className="text-[10px] text-[var(--text-low)] uppercase tracking-wider">distinct matched titles</small>
            </div>
            <div className="py-4 pl-3">
              <b className="block text-2xl text-[var(--text-hi)]">{(totalPlaylists - matchedCount).toLocaleString()}</b>
              <small className="text-[10px] text-[var(--text-low)] uppercase tracking-wider">outside these labels</small>
            </div>
          </div>
          {meta?.categories_overlap && (
            <p className="mb-5 text-xs leading-relaxed text-[var(--text-low)]">
              {assignmentCount.toLocaleString()} category assignments across {matchedCount.toLocaleString()} distinct titles; one title can contribute to several contexts.
            </p>
          )}

          <div className="flex justify-between mb-2 text-[9px] uppercase tracking-[0.12em] text-[var(--text-low)]">
            <span>Share of all playlist titles</span>
            <span>0 — {scaleMax}%</span>
          </div>

          <div className="border-t border-[var(--hairline)]">
            {clusters.map((cluster, index) => {
              const isSelected = selected?.id === cluster.id
              return (
                <button
                  key={cluster.id}
                  onClick={() => {
                    setSelected(cluster)
                    replaceSharedParams({ mood: cluster.id })
                  }}
                  className="mood-evidence-row w-full grid grid-cols-[34px_minmax(130px,0.8fr)_minmax(160px,1.2fr)_76px] gap-3 items-center py-4 border-b border-[var(--hairline)] text-left hover:bg-white/[0.025] focus-visible:bg-white/[0.035]"
                  aria-pressed={isSelected}
                >
                  <span className="text-[10px] text-[var(--text-low)]">0{index + 1}</span>
                  <span>
                    <strong className="block text-sm font-semibold" style={{ color: isSelected ? cluster.color : 'var(--text-hi)' }}>
                      {cluster.label}
                    </strong>
                    <small className="text-[10px] text-[var(--text-low)]">{cluster.count.toLocaleString()} titles</small>
                  </span>
                  <span className="mood-evidence-terms block">
                    <span className="block h-1 bg-white/10">
                      <span
                        className="block h-full"
                        style={{ width: `${(cluster.pct / scaleMax) * 100}%`, background: cluster.color }}
                      />
                    </span>
                    <small className="block mt-2 text-[10px] text-[var(--text-low)] truncate">
                      {(cluster.top_terms || []).slice(0, 4).join(' · ')}
                    </small>
                  </span>
                  <strong className="text-right text-sm" style={{ color: cluster.color }}>{cluster.pct.toFixed(2)}%</strong>
                </button>
              )
            })}
          </div>
        </PvPanel>

        <div className="space-y-4">
          <PvPanel label="What this view means" className="atlas-rise" style={{ '--i': 1 }}>
            <p className="text-sm leading-relaxed text-[var(--text-mid)]">
              These are explicit words found in playlist titles—not an analysis of how the songs sound.
            </p>
            <dl className="mt-5 space-y-4 text-xs">
              <div>
                <dt className="text-[var(--text-hi)] font-semibold">Percentage</dt>
                <dd className="mt-1 text-[var(--text-low)]">Share of the full one-million-playlist corpus.</dd>
              </div>
              <div>
                <dt className="text-[var(--text-hi)] font-semibold">Territory</dt>
                <dd className="mt-1 text-[var(--text-low)]">A practical grouping of related title words.</dd>
              </div>
              <div>
                <dt className="text-[var(--text-hi)] font-semibold">Not shown</dt>
                <dd className="mt-1 text-[var(--text-low)]">Acoustic mood, sentiment, or titles that did not match these vocabularies.</dd>
              </div>
            </dl>
          </PvPanel>

          {selected && (
            <PvPanel label="Selected evidence" className="atlas-rise" style={{ '--i': 2 }}>
              <p className="text-xl font-bold" style={{ color: selected.color }}>{selected.label}</p>
              <p className="text-[var(--text-mid)] text-sm mt-2">{selected.description}</p>
              <p className="text-[var(--text-low)] text-xs mt-3">
                {selected.count.toLocaleString()} matching titles · {selected.pct.toFixed(2)}% of the corpus
              </p>
              <p className="mt-5 mb-2 text-[9px] uppercase tracking-[0.14em] text-[var(--text-low)]">Ranked matching words</p>
              <div className="border-t border-[var(--hairline)]">
                {(selected.top_terms || []).slice(0, 8).map((term, index) => (
                  <div key={term} className="flex gap-3 py-2 border-b border-[var(--hairline)] text-xs">
                    <span className="text-[var(--text-low)]">{index + 1}</span>
                    <span className="text-[var(--text-mid)]">{term}</span>
                  </div>
                ))}
              </div>
            </PvPanel>
          )}
        </div>
      </div>
    </PvPage>
  )
}
