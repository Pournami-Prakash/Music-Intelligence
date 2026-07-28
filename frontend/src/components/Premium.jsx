import { Search } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import EvidencePanel from './EvidencePanel'
import { FEATURE_EVIDENCE } from '../data/featureEvidence'

/**
 * Reusable shell for the clean-premium ("Apple-like") page language.
 * Wraps the `.pv*` classes in index.css so every page converts consistently.
 */

export function PvPage({ children }) {
  const { pathname } = useLocation()
  return (
    <div className="pv">
      {children}
      <EvidencePanel evidence={FEATURE_EVIDENCE[pathname]} pathname={pathname} />
    </div>
  )
}

export function PvTop({ brand = 'Music Intelligence Atlas', sub, pill }) {
  return (
    <div className="pv-top">
      <div className="pv-brand"><b>{brand}</b>{sub ? ` · ${sub}` : ''}</div>
      {pill && <div className="pv-pill">{pill}</div>}
    </div>
  )
}

export function PvHero({ eyebrow, title, children, maxWidth }) {
  return (
    <header className="pv-hero" style={maxWidth ? { maxWidth } : undefined}>
      {eyebrow && <p className="pv-eyebrow">{eyebrow}</p>}
      <h1>{title}</h1>
      {children && <p>{children}</p>}
    </header>
  )
}

export function PvSearch({ value, onChange, onSubmit, placeholder, button = 'Run', loading = false, icon = false, children }) {
  return (
    <form className="pv-search" onSubmit={e => { e.preventDefault(); onSubmit?.() }}>
      {icon ? (
        <div className="pv-search-field">
          <Search size={16} className="text-[var(--text-low)] shrink-0" />
          <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
        </div>
      ) : (
        <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
      )}
      {children}
      <button disabled={!value?.trim() || loading}>{loading ? 'Working…' : button}</button>
    </form>
  )
}

export function PvChips({ items = [], onPick, label = 'Try' }) {
  return (
    <div className="pv-chips">
      {label && <span>{label}</span>}
      {items.map(s => (
        <button key={Array.isArray(s) ? s.join(' → ') : s} onClick={() => onPick(s)}>
          {Array.isArray(s) ? s.join(' → ') : s}
        </button>
      ))}
    </div>
  )
}

export function PvPanel({ label, action, className = '', style, children }) {
  return (
    <section className={`pv-panel ${className}`} style={style}>
      {(label || action) && (
        <div className="flex items-center justify-between">
          {label && <p className="pv-panel-label" style={{ marginBottom: 0 }}>{label}</p>}
          {action}
        </div>
      )}
      {(label || action) && <div style={{ height: 18 }} />}
      {children}
    </section>
  )
}
