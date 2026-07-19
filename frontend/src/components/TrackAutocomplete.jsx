import { useState, useEffect, useId, useRef } from 'react'
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
  const [status, setStatus] = useState('idle')
  const timerRef = useRef(null)
  const wrapRef = useRef(null)
  const justSelectedRef = useRef(false)
  const listId = useId()

  // Debounced fetch
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    if (justSelectedRef.current) { justSelectedRef.current = false; return }
    if (value.trim().length < 2) { setSuggestions([]); setOpen(false); setStatus('idle'); return }
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(async () => {
      setStatus('loading')
      try {
        const res = await fetch(apiUrl(`/api/search-tracks?q=${encodeURIComponent(value)}&limit=8`), { signal: controller.signal })
        if (!res.ok) { setStatus('error'); return }
        const data = await res.json()
        if (cancelled) return
        setSuggestions(data.results || [])
        setOpen(data.results?.length > 0)
        setStatus(data.results?.length > 0 ? 'ready' : 'empty')
        setActive(-1)
      } catch (error) { if (error?.name !== 'AbortError' && !cancelled) setStatus('error') }
    }, 220)
    return () => { cancelled = true; controller.abort(); clearTimeout(timerRef.current) }
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
        aria-label={placeholder.replace('…', '')}
        autoComplete="off"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={active >= 0 ? `${listId}-option-${active}` : undefined}
      />
      <span className="sr-only" role="status" aria-live="polite">
        {status === 'loading' && 'Searching the track catalogue. Long-tail searches may take longer on first use.'}
        {status === 'empty' && 'No matching tracks found.'}
        {status === 'error' && 'Track search is temporarily unavailable.'}
        {status === 'ready' && `${suggestions.length} track suggestions available.`}
      </span>
      {status === 'loading' && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-atlas-muted">SEARCHING</span>}
      {open && suggestions.length > 0 && (
        <ul id={listId} role="listbox" className="absolute left-0 right-0 top-full mt-1 z-50 bg-[#0d0d0c] border border-white/10 shadow-xl max-h-64 overflow-y-auto">
          {suggestions.map((s, i) => (
            <li
              id={`${listId}-option-${i}`}
              role="option"
              aria-selected={i === active}
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
      {!open && status === 'empty' && value.trim().length >= 2 && (
        <p className="absolute left-0 right-0 top-full mt-1 z-40 bg-[#0d0d0c] border border-white/10 px-4 py-3 text-xs text-atlas-muted">
          No matching track in the full catalogue. Check the spelling or try the artist name too.
        </p>
      )}
      {!open && status === 'error' && (
        <p className="absolute left-0 right-0 top-full mt-1 z-40 bg-[#0d0d0c] border border-white/10 px-4 py-3 text-xs text-[#ffb3b6]">
          Track search is unavailable. Try again in a moment.
        </p>
      )}
    </div>
  )
}
