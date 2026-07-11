import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import LottiePlayer from '../components/LottiePlayer'
import { CountUp } from '../components/Observatory'
import { PvPage, PvTop, PvHero, PvSearch, PvChips, PvPanel } from '../components/Premium'
import { errorMessage, getJson } from '../lib/api'

const MOCK_ARTISTS = {
  'Ed Sheeran': { peers: ['Post Malone', 'Drake', 'The Weeknd'] },
  'Taylor Swift': { peers: ['Ariana Grande', 'Olivia Rodrigo', 'Billie Eilish'] },
  'Drake': { peers: ['J. Cole', 'Kendrick Lamar', 'Future'] },
  'Radiohead': { peers: ['Arcade Fire', 'Bon Iver', 'The National'] },
  'Kendrick Lamar': { peers: ['J. Cole', 'Drake', 'Tyler, the Creator'] },
}

// Labels describe playlist ubiquity (how often the artist is reached for),
// not a taste judgment — a niche artist can still be highly playlisted.
const SCORE_LABELS = [
  { min: 95, label: 'Everywhere', color: '#FF7A9C' },
  { min: 85, label: 'Playlist regular', color: '#FB923C' },
  { min: 70, label: 'Widely reached', color: '#F5C451' },
  { min: 50, label: 'Commonly playlisted', color: '#3DDC97' },
  { min: 25, label: 'Niche-leaning', color: '#5AC8FA' },
  { min: 0, label: 'Deep cut', color: '#B08CF8' },
]

const SUGGESTIONS = ['Ed Sheeran', 'Taylor Swift', 'Radiohead', 'Kendrick Lamar', 'Bon Iver']
const scoreLabel = (score) => SCORE_LABELS.find(s => score >= s.min) || SCORE_LABELS[SCORE_LABELS.length - 1]

function Bar({ label, value, color }) {
  return (
    <div className="mb-3 last:mb-0">
      <div className="flex justify-between text-sm mb-1.5">
        <span className="text-[var(--text-mid)]">{label}</span>
        <span style={{ color }}>{Math.round(value)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.min(100, value)}%`, background: color }} />
      </div>
    </div>
  )
}

export default function BasicnessIndex() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const s = location.state
    if (s?.query) { setQuery(s.query); search(s.query) }
  }, [location.state])

  const search = async (q) => {
    if (!q?.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const data = await getJson(`/api/basicness/${encodeURIComponent(q)}`)
      const score = data.percentile
      const tier = scoreLabel(score)
      setResult({
        query: data.query,
        score,
        rank: data.rank,
        total: data.total_artists,
        tier,
        peers: MOCK_ARTISTS[q]?.peers || [],
        diagnosis: `${data.query} sits in the ${score.toFixed(1)}th percentile of ${data.total_artists.toLocaleString()} artists by playlist frequency — ranked #${data.rank}.`,
      })
    } catch (e) {
      const tier = scoreLabel(50)
      setResult({ query: q, score: 50, tier, peers: MOCK_ARTISTS[q]?.peers || [], diagnosis: `Sample data — ${errorMessage(e)}.`, _demo: true })
    } finally {
      setLoading(false)
    }
  }

  return (
    <PvPage>
      <PvTop sub="Artist Observatory" pill="Commonness signal" />
      <PvHero eyebrow="Calibration report" title={result?.query || 'Basicness Index'}>
        A playful mainstream meter for artists — not a judgment, just a measure of how often playlist culture reaches for them.
      </PvHero>

      <PvSearch value={query} onChange={setQuery} onSubmit={() => search(query)} placeholder="Artist name…" button="Rate artist" loading={loading} icon />
      <PvChips items={SUGGESTIONS} onPick={s => { setQuery(s); search(s) }} />

      <div className="max-w-6xl">
        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/formula-pulse.json" className="w-40 h-40 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Calibrating against the playlist mainstream…</p>
            </div>
          </div>
        )}

        {!result && !loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 300 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/pulse-green.json" className="w-32 h-32 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Search an artist to see where they land on the archive's niche → mainstream spectrum.</p>
            </div>
          </div>
        )}

        {result && !loading && (
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4">
            <PvPanel label="Percentile calibration" className="atlas-rise" style={{ '--i': 0 }}>
              {result._demo && <p className="mb-3 text-xs text-[var(--warning)]">{result.diagnosis}</p>}
              <p className="text-7xl sm:text-8xl font-extrabold tracking-[-0.04em] leading-none" style={{ color: result.tier.color }}>
                <CountUp value={result.score} decimals={1} /><span className="text-3xl align-top">th</span>
              </p>
              <p className="text-[var(--text-hi)] text-2xl font-bold mt-2">{result.tier.label}</p>
              {!result._demo && <p className="text-[var(--text-mid)] mt-4 max-w-xl">{result.diagnosis}</p>}
              <div className="mt-6 max-w-xl">
                <Bar label="niche → mainstream" value={result.score} color={result.tier.color} />
                <Bar label="predictability" value={Math.min(99, result.score * 0.88)} color="#3DDC97" />
                <Bar label="cross-playlist familiarity" value={Math.min(99, result.score * 0.92)} color="#F5C451" />
              </div>
            </PvPanel>

            <PvPanel label="Similar tier" className="atlas-rise" style={{ '--i': 1 }}>
              {(result.peers?.length ? result.peers : ['Unknown Mortal Orchestra', 'The Japanese House', 'Still Woozy']).map((peer, index) => (
                <button
                  key={peer}
                  onClick={() => { setQuery(peer); search(peer) }}
                  className="w-full text-left py-3 border-b border-[var(--hairline)] last:border-0 text-[var(--text-mid)] hover:text-[var(--text-hi)]"
                >
                  <span className="text-[var(--text-low)] mr-3 font-mono text-xs">{String(index + 1).padStart(2, '0')}</span>{peer}
                </button>
              ))}
            </PvPanel>
          </div>
        )}
      </div>
    </PvPage>
  )
}
