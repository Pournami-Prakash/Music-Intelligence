const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')

export function apiUrl(url) {
  if (!API_BASE || /^https?:\/\//.test(url)) return url
  return `${API_BASE}${url.startsWith('/') ? url : `/${url}`}`
}

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function getJson(url, options = {}) {
  const controller = new AbortController()
  const timeoutMs = options.timeoutMs ?? 75_000
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  let res
  try {
    res = await fetch(apiUrl(url), { ...options, signal: options.signal || controller.signal })
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new ApiError('The atlas took too long to respond.', 408, 'request_timeout')
    }
    throw new ApiError('The atlas is temporarily unreachable.', 0, 'network_error')
  } finally {
    clearTimeout(timer)
  }
  if (res.ok) return res.json()

  let detail = ''
  try {
    const body = await res.json()
    detail = body.detail || body.message || ''
  } catch {
    // Ignore non-JSON error bodies.
  }
  throw new ApiError(detail || `HTTP ${res.status}`, res.status, detail)
}

export function errorMessage(error) {
  const detail = error?.detail || error?.message
  const messages = {
    artist_not_found: 'That artist is not present in the playlist dataset.',
    track_not_found: 'That track is not present in the playlist dataset.',
    server_busy: 'The demo is handling another large query. Try again in a few seconds.',
    vector_index_not_ready: 'Similarity search is temporarily unavailable.',
    query_vectors_unavailable: 'This track has no embedding, so the atlas cannot compare it.',
    request_timeout: 'The free demo host is still waking up. Try once more in a moment.',
    network_error: 'The atlas is temporarily unreachable. Check your connection and try again.',
  }
  if (typeof detail !== 'string') return 'The atlas could not complete this request.'
  return messages[detail] || detail || 'The atlas could not complete this request.'
}

export function warmBackend() {
  return fetch(apiUrl('/ready'), { priority: 'low' }).catch(() => null)
}

// Precomputed popular examples (frontend/public/data/*-examples.json), keyed by
// the lowercased query. Lets demo-favourite queries render instantly even when
// the free backend is cold/asleep — callers fall back to the live API on a miss.
const _exampleCache = {}
export async function getExample(file, key) {
  if (!key) return null
  if (!_exampleCache[file]) {
    _exampleCache[file] = fetch(`/data/${file}`)
      .then(r => (r.ok ? r.json() : {}))
      .catch(() => ({}))
  }
  try {
    const map = await _exampleCache[file]
    return map[key.toLowerCase().trim()] || null
  } catch {
    return null
  }
}
