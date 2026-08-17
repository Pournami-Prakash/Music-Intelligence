import { useEffect, useState } from 'react'
import ShareResult from './ShareResult'
import { getAtlasMetadata } from '../lib/api'

const MODEL_ASSISTED = new Set(['/genre-weather', '/soundtrack-gift', '/transition', '/doppelganger'])
const CONTEXTUAL = new Set([
  '/mood-map', '/ancestry', '/artist-habitat', '/mood-contradiction',
  '/guilty-pleasure', '/playlist-language', '/name-generator', '/roast',
])

function confidenceFor(pathname) {
  if (MODEL_ASSISTED.has(pathname)) return ['Model-assisted', 'Similarity or audio model with disclosed coverage']
  if (CONTEXTUAL.has(pathname)) return ['Contextual', 'Observed counts interpreted through declared title or tag rules']
  return ['Measured', 'Direct count, rank, date, or graph relationship']
}

// The vintage of the data, not the day the artifacts were compiled. Showing the
// build date read as "Corpus 2026", which invited people to treat a playlist
// archive that ends in 2017 as current, which is why a 2021 artist looks obscure
// here. Routes served from the ongoing editorial archive are dated separately.
const PLAYLIST_CORPUS_SPAN = 'Playlists 2010–2017'
const EDITORIAL_SPAN = 'Editorial archive to 2026'

// Routes whose evidence comes from the editorial archive rather than the
// one-million-playlist corpus, and so are not bounded by the 2017 cutoff.
const EDITORIAL_SOURCED = new Set([
  '/editorial-graveyard', '/forgotten-hits', '/forensics',
  '/mood-contradiction', '/guilty-pleasure',
])

function formatSnapshot(value, pathname) {
  if (pathname === '/listening') return 'Your own export'
  const span = EDITORIAL_SOURCED.has(pathname) ? EDITORIAL_SPAN : PLAYLIST_CORPUS_SPAN
  if (!value) return span
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return span
  return `${span} · built ${new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: 'short',
  }).format(date)}`
}

export default function EvidencePanel({ evidence, pathname }) {
  const [snapshot, setSnapshot] = useState('Loading corpus date…')
  const [confidence, confidenceBasis] = confidenceFor(pathname)

  useEffect(() => {
    let active = true
    getAtlasMetadata().then(meta => {
      if (active) setSnapshot(formatSnapshot(meta?.manifest_generated_at, pathname))
    })
    return () => { active = false }
  }, [pathname])

  if (!evidence) return null

  return (
    <section className="atlas-evidence-contract max-w-6xl">
      <div className="atlas-evidence-status" aria-label="Result provenance">
        <span data-confidence={confidence.toLowerCase()}>{confidence} confidence</span>
        <span>{snapshot}</span>
        <ShareResult />
      </div>
      <details>
        <summary>
          <span>Evidence contract</span>
          <span className="atlas-evidence-summary">How this result should be read</span>
        </summary>
        <dl>
          <div>
            <dt>Metric</dt>
            <dd>{evidence.metric}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{evidence.source}</dd>
          </div>
          <div>
            <dt>Coverage</dt>
            <dd>{evidence.coverage}</dd>
          </div>
          <div>
            <dt>Do not infer</dt>
            <dd>{evidence.limit}</dd>
          </div>
          <div>
            <dt>Confidence basis</dt>
            <dd>{confidenceBasis}</dd>
          </div>
        </dl>
      </details>
    </section>
  )
}
