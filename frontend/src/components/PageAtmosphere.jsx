export default function PageAtmosphere({ scene }) {
  const [motif, code, descriptor] = scene

  return (
    <div className="atlas-atmosphere" data-motif={motif} aria-hidden="true">
      <div className="atlas-route-stamp">
        <span>{code}</span>
        <small>{descriptor}</small>
      </div>
      <div className="atlas-motif">
        <i className="atlas-shape atlas-shape-a" />
        <i className="atlas-shape atlas-shape-b" />
        <i className="atlas-shape atlas-shape-c" />
        <i className="atlas-shape atlas-shape-d" />
      </div>
      <div className="atlas-coordinate-rail">
        <span>41.8781° N</span><span>ARCHIVE SIGNAL</span><span>87.6298° W</span>
      </div>
    </div>
  )
}
