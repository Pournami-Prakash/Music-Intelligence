import { useEffect, useRef, useState } from 'react'
import { Link2 } from 'lucide-react'

function resultUrl(params = {}) {
  const url = new URL(window.location.href)
  Object.entries(params).forEach(([key, value]) => {
    if (value == null || !String(value).trim()) url.searchParams.delete(key)
    else url.searchParams.set(key, String(value).trim())
  })
  return url.toString()
}

export default function ShareResult({ params, label = 'Copy result link', className = '' }) {
  const [status, setStatus] = useState('')
  const resetTimer = useRef(null)

  useEffect(() => () => window.clearTimeout(resetTimer.current), [])

  const copy = async () => {
    const value = resultUrl(params)
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      const input = document.createElement('textarea')
      input.value = value
      input.setAttribute('readonly', '')
      input.style.position = 'fixed'
      input.style.opacity = '0'
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      input.remove()
    }
    setStatus('Link copied')
    window.clearTimeout(resetTimer.current)
    resetTimer.current = window.setTimeout(() => setStatus(''), 1800)
  }

  return (
    <span className={`atlas-share-wrap ${className}`}>
      <button type="button" className="atlas-share-result" onClick={copy}>
        <Link2 size={13} aria-hidden="true" />
        {status || label}
      </button>
      <span className="sr-only" aria-live="polite">{status}</span>
    </span>
  )
}
