import { useState, useEffect, useRef } from 'react'
import { apiUrl } from '../lib/api'

/**
 * Controlled input with live track autocomplete from /api/search-tracks.
 * Props:
 *   value, onChange(str), onSelect({title, artist, uri}), placeholder
 */
export default function TrackAutocomplete({ value, onChange, onSelect, placeholder = 'Track name…' }) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const timerRef = useRef(null)
  const wrapRef = useRef(null)
  const justSelectedRef = useRef(false)

  // Debounced fetch
  useEffect(() => {
    if (justSelectedRef.current) { justSelectedRef.current = false; return }
    if (value.trim().length < 2) { setSuggestions([]); setOpen(false); return }
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(async () => {
      try {
        const res = await fetch(apiUrl(`/api/search-tracks?q=${encodeURIComponent(value)}&limit=8`))
        if (!res.ok) return
        const data = await res.json()
        setSuggestions(data.results || [])
        setOpen(data.results?.length > 0)
        setActive(-1)
      } catch { /* ignore */ }
    }, 220)
    return () => clearTimeout(timerRef.current)
  }, [value])

  // Close on outside click
  useEffect(() => {
    const handler = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const pick = (item) => {
    justSelectedRef.current = true
    onChange(item.title)
    setSuggestions([])
    setOpen(false)
    setActive(-1)
    onSelect?.(item)
  }

  const handleKey = (e) => {
    if (!open) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(i => Math.min(i + 1, suggestions.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(i => Math.max(i - 1, -1)) }
    else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); pick(suggestions[active]) }
    else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div ref={wrapRef} className="relative flex-1">
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={handleKey}
        onFocus={() => suggestions.length > 0 && setOpen(true)}
        placeholder={placeholder}
        autoComplete="off"
      />
      {open && suggestions.length > 0 && (
        <ul className="absolute left-0 right-0 top-full mt-1 z-50 bg-[#0d0d0c] border border-white/10 shadow-xl max-h-64 overflow-y-auto">
          {suggestions.map((s, i) => (
            <li
              key={`${s.title}-${s.artist}`}
              onClick={() => pick(s)}
              className={`flex items-baseline gap-3 px-4 py-2.5 cursor-pointer text-sm transition-colors ${
                i === active ? 'bg-white/10 text-atlas-heading' : 'text-atlas-text hover:bg-white/[0.05]'
              }`}
            >
              <span className="truncate font-medium">{s.title}</span>
              <span className="text-atlas-muted text-xs flex-shrink-0 truncate max-w-[40%]">{s.artist}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
