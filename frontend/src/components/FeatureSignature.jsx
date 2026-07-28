import { useEffect, useRef } from 'react'
import { animate as anime, stagger } from 'animejs'
import { getFeatureProfile } from '../data/featureProfiles'

const DOTS = [
  [34, 84], [74, 43], [118, 72], [166, 34], [212, 68], [262, 40],
]

function SignatureMarks({ kind }) {
  switch (kind) {
    case 'territory':
      return <>
        <path d="M18 96c24-68 82-78 112-34s85 46 104-2 62-34 74 18" />
        <path d="M6 126c42-46 91-49 126-20s83 30 112 4 56-17 74 4" />
        <path d="M32 150c52-26 98-18 132 0s76 16 116-5" />
      </>
    case 'pressure':
      return <>
        <circle cx="90" cy="92" r="52" /><circle cx="90" cy="92" r="30" />
        <circle cx="232" cy="76" r="62" /><circle cx="232" cy="76" r="37" />
        <path d="M8 142c62-30 106-18 142 1s92 17 162-13" strokeDasharray="3 7" />
      </>
    case 'lineage':
      return <>
        <path d="M22 92h54l34-48 48 48 48-34 46 34h54" />
        {DOTS.map(([cx, cy]) => <circle key={cx} cx={cx} cy={cy} r="5" className="signature-node" />)}
      </>
    case 'scanner':
      return <>
        {[26, 50, 74, 98, 122, 146].map((y, i) => <path key={y} d={`M22 ${y}h${80 + i * 34}`} />)}
        <rect x="130" y="18" width="78" height="142" className="signature-scan" />
      </>
    case 'radar':
    case 'compass':
      return <>
        <circle cx="160" cy="88" r="70" /><circle cx="160" cy="88" r="46" /><circle cx="160" cy="88" r="20" />
        <path d="M160 8v160M80 88h160" />
        <path d="M160 88L232 42" className="signature-needle" />
      </>
    case 'bubbles':
      return <>
        <circle cx="78" cy="82" r="48" /><circle cx="172" cy="62" r="34" /><circle cx="236" cy="112" r="52" />
        <circle cx="142" cy="126" r="24" />
      </>
    case 'gauge':
    case 'score':
      return <>
        <path d="M42 132a118 118 0 0 1 236 0" strokeWidth="8" />
        <path d="M160 132l76-72" className="signature-needle" />
        <circle cx="160" cy="132" r="10" />
        {kind === 'score' && <path d="M54 36l214 104" strokeWidth="3" />}
      </>
    case 'spotlight':
      return <>
        <path d="M132 8h56l92 154H40z" />
        <circle cx="160" cy="54" r="25" />
        <ellipse cx="160" cy="152" rx="88" ry="18" />
      </>
    case 'overlap':
    case 'impact':
      return <>
        <circle cx={kind === 'impact' ? 126 : 112} cy="88" r="68" />
        <circle cx={kind === 'impact' ? 194 : 208} cy="88" r="68" />
        <path d="M160 18v140" strokeDasharray="2 6" />
      </>
    case 'passport':
      return <>
        <rect x="50" y="18" width="220" height="142" transform="rotate(-3 160 89)" />
        <circle cx="210" cy="78" r="42" strokeDasharray="5 5" />
        <path d="M76 54h78M76 76h54M76 118h112" />
      </>
    case 'fault':
      return <>
        <path d="M4 84c34 0 34-52 68-52s34 96 68 96 34-78 68-78 34 34 68 34h40" />
        <path d="M158 6l-20 46 34 18-28 42 26 50" strokeWidth="3" />
      </>
    case 'heat':
    case 'matrix':
    case 'slots':
      return <>
        {[0, 1, 2, 3].flatMap(row => [0, 1, 2, 3, 4, 5].map(col => (
          <rect
            key={`${row}-${col}`}
            x={24 + col * 46}
            y={20 + row * 34}
            width={kind === 'slots' ? 34 : 30}
            height={kind === 'slots' ? 92 : 22}
            opacity={.18 + ((row + col * 2) % 5) * .15}
            className="signature-cell"
          />
        )))}
      </>
    case 'arc':
    case 'bridge':
      return <>
        <circle cx="42" cy="118" r="10" /><circle cx="278" cy="42" r="10" />
        <path d="M42 118C92 12 214 158 278 42" strokeWidth="3" />
        <path d="M54 122C112 58 190 126 262 50" strokeDasharray="4 7" />
      </>
    case 'trend':
    case 'decay':
      return <>
        <path d={kind === 'trend' ? 'M16 142L72 122l42 10 52-62 50 18 86-70' : 'M16 30l50 18 44 20 52 12 56 35 84 28'} strokeWidth="3" />
        <path d="M16 154h286M16 18v136" />
      </>
    case 'path':
      return <>
        <path d="M24 126L78 76l50 28 48-66 54 54 68-46" strokeWidth="3" />
        {[[24,126],[78,76],[128,104],[176,38],[230,92],[298,46]].map(([cx,cy]) => <circle key={cx} cx={cx} cy={cy} r="7" className="signature-node" />)}
      </>
    case 'mirror':
      return <>
        <path d="M160 10v150" strokeDasharray="3 6" />
        <path d="M28 126c42-98 82-98 116 0M292 126c-42-98-82-98-116 0" />
        <circle cx="90" cy="88" r="24" /><circle cx="230" cy="88" r="24" />
      </>
    case 'blend':
      return <>
        <circle cx="116" cy="70" r="58" /><circle cx="204" cy="70" r="58" /><circle cx="160" cy="128" r="58" />
        <circle cx="160" cy="91" r="11" className="signature-node" />
      </>
    case 'ledger':
      return <>
        {[28, 54, 80, 106, 132].map((y, i) => <path key={y} d={`M24 ${y}h${260 - i * 22}`} />)}
        <path d="M52 16v140M228 16v140" strokeDasharray="2 5" />
      </>
    case 'capsule':
      return <>
        <circle cx="160" cy="88" r="74" /><circle cx="160" cy="88" r="50" /><circle cx="160" cy="88" r="25" />
        <path d="M160 88L220 36" className="signature-needle" />
        <path d="M74 152h172" />
      </>
    default:
      return <path d="M20 88h280" />
  }
}

export default function FeatureSignature({ scene }) {
  const profile = getFeatureProfile(scene.key)
  const rootRef = useRef(null)

  useEffect(() => {
    const root = rootRef.current
    if (!root || !profile || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined
    const run = (selector, options) => {
      const targets = root.querySelectorAll(selector)
      return targets.length ? anime(targets, options) : null
    }
    const animations = [
      run('path, circle, rect', {
        opacity: [0, .72],
        scale: [.94, 1],
        delay: stagger(18),
        duration: 520,
        ease: 'outExpo',
      }),
      run('.signature-node', {
        scale: [.92, 1.08, .92],
        opacity: [.34, .58, .34],
        delay: stagger(340),
        duration: 4800,
        loop: true,
        ease: 'inOutSine',
      }),
      run('.signature-needle', {
        rotate: ['-2deg', '2deg', '-2deg'],
        duration: 7200,
        loop: true,
        ease: 'inOutSine',
      }),
      run('.signature-scan', {
        translateX: [-48, 64],
        opacity: [.04, .18, .04],
        duration: 4200,
        loop: true,
        ease: 'inOutSine',
      }),
    ].filter(Boolean)
    return () => animations.forEach(animation => animation?.cancel?.())
  }, [profile, scene.key])

  if (!profile) return null

  return (
    <div className="feature-signature" ref={rootRef} data-signature={profile.kind}>
      <div className="feature-signature-head">
        <span>{profile.instrument}</span>
        <b>{profile.readout}</b>
      </div>
      <svg viewBox="0 0 320 176" aria-hidden="true">
        <SignatureMarks kind={profile.kind} />
      </svg>
      <p>{profile.note}</p>
    </div>
  )
}
