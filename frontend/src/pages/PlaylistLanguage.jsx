import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { PvPage, PvTop, PvHero, PvPanel } from '../components/Premium'
import { apiUrl } from '../lib/api'

const WORDS = [
  { word: 'vibes', freq: 94120, cat: 'mood', examples: ['sunday vibes', 'late night vibes', 'beach vibes only'] },
  { word: 'chill', freq: 87340, cat: 'mood', examples: ['chill study beats', 'chill sunday', 'just chill'] },
  { word: 'love', freq: 82340, cat: 'mood', examples: ['love songs', 'falling in love', 'old love'] },
  { word: 'sad', freq: 76230, cat: 'mood', examples: ['sad songs for crying', 'sad bops', 'sad girl fall'] },
  { word: 'workout', freq: 68930, cat: 'activity', examples: ['gym motivation', 'leg day hits', 'workout energy'] },
  { word: 'study', freq: 65210, cat: 'activity', examples: ['study focus', 'library hours', 'study with me'] },
  { word: 'party', freq: 54120, cat: 'activity', examples: ['party classics', 'pregame', 'house party'] },
  { word: 'summer', freq: 47230, cat: 'time', examples: ['summer nights', 'summer 2016', 'beach summer'] },
  { word: 'indie', freq: 62140, cat: 'genre', examples: ['indie sleaze', 'indie pop', 'indie roadtrip'] },
  { word: 'era', freq: 43120, cat: 'identity', examples: ['new era', 'villain era', 'healing era'] },
]

const CATS = ['all', 'mood', 'activity', 'time', 'identity', 'genre']
const CAT_COLORS = { mood: '#FF7A9C', activity: '#3DDC97', time: '#5AC8FA', identity: '#B08CF8', genre: '#F5C451' }

export default function PlaylistLanguage() {
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [words, setWords] = useState(WORDS)
  const location = useLocation()

  useEffect(() => {
    if (location.state?.filter) setFilter(location.state.filter)
    fetch(apiUrl(`/api/playlist-language?limit=80`))
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.words?.length) {
          setWords(data.words.map(w => ({ word: w.word, freq: w.freq, cat: w.cat, examples: w.examples || [] })))
        }
      })
      .catch(() => {})
  }, [location.state])

  const filtered = filter === 'all' ? words : words.filter(w => w.cat === filter)
  const maxFreq = Math.max(...words.map(w => w.freq), 1)
  const active = selected || filtered[0]
  const categoryTotals = Object.keys(CAT_COLORS).map(cat => ({
    cat, total: words.filter(w => w.cat === cat).reduce((sum, w) => sum + w.freq, 0),
  }))
  const maxCat = Math.max(...categoryTotals.map(c => c.total), 1)

  return (
    <PvPage>
      <PvTop sub="Vibe Dictionary" pill="1M names" />
      <PvHero eyebrow="Phrase evidence" title="Playlist Language">
        Read the public vocabulary of playlists — moods, rituals, time-of-day signals, identity tags, and genre shortcuts.
      </PvHero>

      <div className="max-w-6xl">
        <div className="flex gap-2 flex-wrap mb-4">
          {CATS.map(cat => (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className="px-4 py-2 rounded-full text-sm capitalize border transition-colors"
              style={{
                borderColor: filter === cat ? '#FB923C' : 'var(--hairline)',
                background: filter === cat ? '#FB923C22' : 'rgba(255,255,255,0.03)',
                color: filter === cat ? '#FB923C' : 'var(--text-mid)',
              }}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4 items-start">
          <PvPanel label="Language field" className="atlas-rise" style={{ '--i': 0 }}>
            <div className="min-h-[420px] flex flex-wrap gap-x-5 gap-y-4 content-center items-baseline justify-center">
              {filtered.map(w => {
                const size = 13 + (w.freq / maxFreq) * 34
                const isActive = active?.word === w.word
                return (
                  <button
                    key={w.word}
                    onClick={() => setSelected(w)}
                    className="leading-none transition-transform hover:scale-105"
                    style={{
                      fontSize: `${size}px`,
                      color: isActive ? CAT_COLORS[w.cat] : 'var(--text-hi)',
                      opacity: active && !isActive ? 0.4 : 0.95,
                      fontWeight: w.freq > 60000 ? 800 : 600,
                    }}
                  >
                    {w.word}
                  </button>
                )
              })}
            </div>
          </PvPanel>

          <div className="space-y-4">
            <PvPanel label="Selected phrase" className="atlas-rise" style={{ '--i': 1 }}>
              {active && (
                <>
                  <p className="text-3xl font-extrabold tracking-[-0.03em]" style={{ color: CAT_COLORS[active.cat] || 'var(--text-hi)' }}>{active.word}</p>
                  <p className="text-[var(--text-mid)] text-sm mt-1">{active.freq.toLocaleString()} playlist names · {active.cat}</p>
                  <div className="mt-4 space-y-2">
                    {(active.examples?.length ? active.examples : ['No examples in this sample yet']).slice(0, 4).map((ex, i) => (
                      <p key={`${ex}-${i}`} className="text-sm text-[var(--text-mid)] border-b border-[var(--hairline)] pb-2 last:border-0">
                        <span className="text-[var(--text-low)] mr-2 font-mono text-xs">{String(i + 1).padStart(2, '0')}</span>{ex}
                      </p>
                    ))}
                  </div>
                </>
              )}
            </PvPanel>

            <PvPanel label="Theme balance" className="atlas-rise" style={{ '--i': 2 }}>
              {categoryTotals.map(({ cat, total }) => (
                <div key={cat} className="mb-3 last:mb-0">
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="text-[var(--text-mid)] capitalize">{cat}</span>
                    <span style={{ color: CAT_COLORS[cat] }}>{Math.round((total / maxCat) * 100)}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${(total / maxCat) * 100}%`, background: CAT_COLORS[cat] }} />
                  </div>
                </div>
              ))}
            </PvPanel>
          </div>
        </div>
      </div>
    </PvPage>
  )
}
