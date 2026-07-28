const GLYPHS = {
  cartography: (
    <>
      <path d="M20 116C62 42 110 24 174 42s94 10 126-22" />
      <path d="M4 150c54-68 108-82 168-55s105 22 144-10" />
      <path d="M30 184c62-50 111-55 166-29s86 29 116 10" />
    </>
  ),
  observatory: (
    <>
      <ellipse cx="160" cy="100" rx="132" ry="64" />
      <ellipse cx="160" cy="100" rx="88" ry="42" transform="rotate(-24 160 100)" />
      <path d="M18 100h284M160 8v184" />
      <circle cx="232" cy="60" r="5" className="environment-node" />
    </>
  ),
  song: (
    <>
      <path d="M8 112c28 0 28-48 56-48s28 82 56 82 28-108 56-108 28 76 56 76 28-44 56-44 28 34 56 34" />
      <path d="M8 140c42 0 42-38 84-38s42 54 84 54 42-72 84-72 42 38 84 38" />
    </>
  ),
  lexicon: (
    <>
      <path d="M24 38h272M24 76h176M24 114h244M24 152h132" />
      <path d="M48 18v164M128 18v164M208 18v164M288 18v164" strokeDasharray="2 8" />
    </>
  ),
  graph: (
    <>
      <path d="M28 142L88 62l64 52 56-84 82 92" />
      <path d="M28 142l124-28 138 8M88 62l120-32" />
      {[['28','142'], ['88','62'], ['152','114'], ['208','30'], ['290','122']].map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="5" className="environment-node" />
      ))}
    </>
  ),
  archive: (
    <>
      <rect x="28" y="28" width="104" height="144" />
      <rect x="108" y="18" width="104" height="154" />
      <rect x="188" y="38" width="104" height="134" />
      <path d="M44 58h72M44 78h52M124 52h72M124 72h48M204 68h72M204 88h44" />
    </>
  ),
}

export default function EnvironmentGlyph({ family }) {
  return (
    <svg className="atlas-environment-svg" viewBox="0 0 320 200" aria-hidden="true">
      <g>{GLYPHS[family] || GLYPHS.observatory}</g>
    </svg>
  )
}
