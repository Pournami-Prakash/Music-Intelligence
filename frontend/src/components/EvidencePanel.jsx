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

function formatSnapshot(value) {
  if (!value) return 'Snapshot date unavailable'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Snapshot date unavailable'
  return `Corpus ${new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  }).format(date)}`
}

export default function EvidencePanel({ evidence, pathname }) {
  const [snapshot, setSnapshot] = useState('Loading corpus date…')
  const [confidence, confidenceBasis] = confidenceFor(pathname)

  useEffect(() => {
    let active = true
    getAtlasMetadata().then(meta => {
      if (active) setSnapshot(formatSnapshot(meta?.manifest_generated_at))
    })
    return () => { active = false }
  }, [])

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
