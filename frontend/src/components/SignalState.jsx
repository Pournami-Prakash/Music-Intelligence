import { Search } from 'lucide-react'

export function QueryDock({
  value,
  onChange,
  onSubmit,
  placeholder,
  buttonLabel = 'Run',
  loading = false,
  disabled = false,
  children,
}) {
  return (
    <div className="atlas-query-dock">
      <div className="atlas-query-input">
        <Search size={15} />
        <input
          value={value}
          onChange={onChange}
          onKeyDown={e => e.key === 'Enter' && onSubmit?.()}
          placeholder={placeholder}
        />
      </div>
      {children}
      <button onClick={onSubmit} disabled={disabled || loading}>
        {loading ? 'Searching...' : buttonLabel}
      </button>
    </div>
  )
}

export function SuggestionStrip({ suggestions, onPick }) {
  return (
    <div className="atlas-suggestion-strip">
      <span>Try</span>
      {suggestions.map(s => (
        <button key={Array.isArray(s) ? s.join(' -> ') : s} onClick={() => onPick(s)}>
          {Array.isArray(s) ? s.join(' -> ') : s}
        </button>
      ))}
    </div>
  )
}

export function EmptySignal({ children }) {
  return (
    <div className="atlas-empty-signal">
      <span />
      <p>{children}</p>
    </div>
  )
}

export function LoadingSignal({ children }) {
  return (
    <div className="atlas-loading-signal">
      <i />
      <p>{children}</p>
    </div>
  )
}

export function ErrorSignal({ children, detail, onRetry, retryLabel = 'Try again' }) {
  return (
    <div className="atlas-error-signal" role="alert">
      <div>
        <p>{children}</p>
        {detail && <small>{detail}</small>}
        {onRetry && (
          <button type="button" onClick={onRetry}>{retryLabel}</button>
        )}
      </div>
    </div>
  )
}
