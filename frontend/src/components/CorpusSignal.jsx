import { useEffect, useRef, useState } from 'react'
import { animate as anime, stagger as animeStagger } from 'animejs'

const SIGNALS = [
  { artist: 'Drake', context: 'late-night / workout', reach: '84.2%', x: 73, y: 28, size: 7 },
  { artist: 'Radiohead', context: 'rainy / introspective', reach: '61.8%', x: 78, y: 65, size: 6 },
  { artist: 'Taylor Swift', context: 'main character / pop', reach: '92.4%', x: 29, y: 22, size: 8 },
  { artist: 'Kendrick Lamar', context: 'focus / lyrical', reach: '74.1%', x: 19, y: 58, size: 6 },
  { artist: 'Charli xcx', context: 'party / hyperpop', reach: '55.7%', x: 48, y: 78, size: 5 },
]

const PATHS = [
  'M50 49 Q59 31 73 28',
  'M50 49 Q68 50 78 65',
  'M50 49 Q42 27 29 22',
  'M50 49 Q34 48 19 58',
  'M50 49 Q42 66 48 78',
  'M29 22 Q51 13 73 28',
  'M19 58 Q48 73 78 65',
]

export default function CorpusSignal() {
  const rootRef = useRef(null)
  const [active, setActive] = useState(0)

  useEffect(() => {
    const root = rootRef.current
    if (!root) return undefined
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) return undefined

    const animations = [
      anime(root.querySelectorAll('.corpus-path'), {
        strokeDashoffset: [180, 0],
        opacity: [0, 0.62],
        delay: animeStagger(90),
        duration: 1050,
        ease: 'outExpo',
      }),
      anime(root.querySelectorAll('.corpus-node'), {
        opacity: [0, 1],
        scale: [0.3, 1],
        delay: animeStagger(105, { start: 260 }),
        duration: 760,
        ease: 'outExpo',
      }),
      anime(root.querySelector('.corpus-reticle'), {
        rotate: '1turn',
        duration: 24000,
        loop: true,
        ease: 'linear',
      }),
      anime(root.querySelectorAll('.corpus-ping'), {
        scale: [0.65, 1.9],
        opacity: [0.55, 0],
        delay: animeStagger(650),
        duration: 2300,
        loop: true,
        ease: 'outQuad',
      }),
    ]

    const cycle = window.setInterval(() => {
      setActive(current => (current + 1) % SIGNALS.length)
    }, 3100)

    return () => {
      window.clearInterval(cycle)
      animations.forEach(animation => animation?.cancel?.())
    }
  }, [])

  const handlePointerMove = event => {
    const rect = event.currentTarget.getBoundingClientRect()
    event.currentTarget.style.setProperty('--signal-x', `${((event.clientX - rect.left) / rect.width) * 100}%`)
    event.currentTarget.style.setProperty('--signal-y', `${((event.clientY - rect.top) / rect.height) * 100}%`)
  }

  const signal = SIGNALS[active]

  return (
    <div
      className="corpus-signal"
      ref={rootRef}
      onPointerMove={handlePointerMove}
      onPointerLeave={event => {
        event.currentTarget.style.removeProperty('--signal-x')
        event.currentTarget.style.removeProperty('--signal-y')
      }}
    >
      <div className="corpus-console-head">
        <span><i /> Corpus signal</span>
        <b>Live sample / 005</b>
      </div>

      <div className="corpus-plot">
        <svg viewBox="0 0 100 100" role="img" aria-labelledby="corpus-title corpus-desc">
          <title id="corpus-title">A sample map of artist relationships</title>
          <desc id="corpus-desc">Five artists connected to a central playlist corpus, illustrating the atlas relationship graph.</desc>
          <defs>
            <radialGradient id="corpus-core">
              <stop offset="0" stopColor="#dfffe5" stopOpacity=".95" />
              <stop offset=".35" stopColor="#53e076" stopOpacity=".5" />
              <stop offset="1" stopColor="#53e076" stopOpacity="0" />
            </radialGradient>
          </defs>

          <g className="corpus-grid" aria-hidden="true">
            <circle cx="50" cy="49" r="15" />
            <circle cx="50" cy="49" r="29" />
            <circle cx="50" cy="49" r="43" />
            <path d="M5 49H95M50 4V94" />
          </g>

          <g aria-hidden="true">
            {PATHS.map(path => <path key={path} className="corpus-path" d={path} pathLength="180" />)}
          </g>

          <g className="corpus-reticle" aria-hidden="true">
            <path d="M50 7A42 42 0 0 1 92 49" />
            <path d="M50 91A42 42 0 0 1 8 49" />
          </g>

          <g className="corpus-core" aria-hidden="true">
            <circle cx="50" cy="49" r="14" fill="url(#corpus-core)" />
            <circle className="corpus-ping" cx="50" cy="49" r="7" />
            <circle cx="50" cy="49" r="3.5" />
          </g>

          {SIGNALS.map((item, index) => (
            <g
              className={`corpus-node ${index === active ? 'is-active' : ''}`}
              key={item.artist}
              style={{ transformOrigin: `${item.x}px ${item.y}px` }}
              onClick={() => setActive(index)}
              role="button"
              tabIndex="0"
              aria-label={`Inspect ${item.artist} signal`}
              onKeyDown={event => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  setActive(index)
                }
              }}
            >
              <circle className="corpus-ping" cx={item.x} cy={item.y} r={item.size + 2} />
              <circle className="corpus-node-hit" cx={item.x} cy={item.y} r={item.size + 5} />
              <circle className="corpus-node-dot" cx={item.x} cy={item.y} r={item.size / 2} />
              <text x={item.x} y={item.y + (item.y > 60 ? 10 : -8)} textAnchor="middle">{String(index + 1).padStart(2, '0')}</text>
            </g>
          ))}
        </svg>

        <div className="corpus-readout" aria-live="polite">
          <span>Signal {String(active + 1).padStart(2, '0')}</span>
          <strong>{signal.artist}</strong>
          <p>{signal.context}</p>
          <b>{signal.reach} <small>corpus reach</small></b>
        </div>
      </div>

      <div className="corpus-console-foot">
        <span>66.3M co-occurrences</span>
        <span>confidence 0.94</span>
        <span>updated now</span>
      </div>
    </div>
  )
}
