import { useState, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { errorMessage, getJson } from '../lib/api'

const ACCENT = '#FB923C'
const THEMES = ['chill', 'sad', 'hype', 'romantic', 'gym', 'party', 'study', 'summer', 'nostalgic']

export default function PlaylistNameGenerator() {
  const [theme, setTheme] = useState(null)
  const [names, setNames] = useState([])
  const [source, setSource] = useState('')
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(null)
  const location = useLocation()

  const generate = useCallback(async (t) => {
    setLoading(true)
    setNames([])
    setSource('')
    try {
      const qs = t ? `?theme=${encodeURIComponent(t)}&count=12` : '?count=12'
      const data = await getJson(`/api/name-generator${qs}`)
      setNames(data.names || [])
      setSource(data.source || '')
    } catch (e) {
      setNames([])
      setSource(`Live endpoint unavailable — ${errorMessage(e)}.`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const s = location.state
    if (s?.theme || s?.mood) { const t = s.theme || s.mood; setTheme(t); generate(t) }
  }, [location.state, generate])

  const pick = (t) => { setTheme(t); generate(t) }

  const copy = (name) => {
    navigator.clipboard?.writeText(name)
    setCopied(name)
    setTimeout(() => setCopied(null), 2000)
  }

  return (
    <PvPage>
      <PvTop sub="Vibe Dictionary" pill="Phrase machine" />
      <PvHero eyebrow="Name synthesis" title="Playlist Name Generator">
        Pick a theme and remix real playlist-title terms, drawn from a million titles named 2010–2017.
      </PvHero>

      <div className="max-w-6xl">
        <div className="flex flex-wrap gap-2 mb-4">
          {THEMES.map(t => (
            <button
              key={t}
              onClick={() => pick(t)}
              className="px-4 py-2 rounded-full text-sm border capitalize transition-colors"
              style={{
                borderColor: theme === t ? ACCENT : 'var(--hairline)',
                background: theme === t ? `${ACCENT}22` : 'rgba(255,255,255,0.03)',
                color: theme === t ? ACCENT : 'var(--text-mid)',
              }}
            >
              {t}
            </button>
          ))}
        </div>

        {loading && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 280 }}>
            <div className="text-center">
              <LottiePlayer src="/assets/formula-pulse.json" className="w-36 h-36 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">Synthesising names…</p>
            </div>
          </div>
        )}

        {!loading && names.length === 0 && (
          <div className="pv-panel grid place-items-center" style={{ minHeight: 280 }}>
            <div className="text-center max-w-md">
              <LottiePlayer src="/assets/pulse-green.json" className="w-32 h-32 mx-auto" />
              <p className="mt-2 text-[var(--text-mid)]">{source || 'Pick a theme to generate playlist names.'}</p>
              {theme && <p className="mt-2 text-xs text-[var(--text-low)]">Every result includes a {theme} anchor and a companion term observed in the matching corpus category.</p>}
            </div>
          </div>
        )}

        {!loading && names.length > 0 && (
          <PvPanel className="atlas-rise" style={{ '--i': 0 }}>
            <div className="flex items-center justify-between mb-4">
              <p className="pv-panel-label" style={{ marginBottom: 0 }}>{theme ? `${theme} names` : 'Generated names'}</p>
              <button onClick={() => generate(theme)} className="flex items-center gap-1.5 text-xs text-[var(--text-mid)] hover:text-[var(--text-hi)]">
                <RefreshCw size={13} /> Shuffle
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {names.map((name, i) => (
                <button
                  key={name + i}
                  onClick={() => copy(name)}
                  className="text-left rounded-xl border bg-black/20 px-4 py-3 flex items-center justify-between group transition-colors hover:bg-white/[0.04]"
                  style={{ borderColor: copied === name ? ACCENT : 'var(--hairline)' }}
                >
                  <span className="text-[var(--text-hi)] text-sm">{name}</span>
                  <span className="text-[10px] font-semibold flex-shrink-0 ml-3" style={{ color: copied === name ? ACCENT : 'var(--text-low)' }}>
                    {copied === name ? 'Copied' : 'Copy'}
                  </span>
                </button>
              ))}
            </div>
            {source && <p className="text-[var(--text-low)] text-xs mt-4">Source: {source}</p>}
          </PvPanel>
        )}
      </div>
    </PvPage>
  )
}
