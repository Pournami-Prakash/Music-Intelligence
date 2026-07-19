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
  // Chain a caller-supplied signal INTO our controller so the timeout still
  // fires (previously passing options.signal silently disabled the timeout).
  if (options.signal) {
    if (options.signal.aborted) controller.abort()
    else options.signal.addEventListener('abort', () => controller.abort(), { once: true })
  }
  let res
  try {
    res = await fetch(apiUrl(url), { ...options, signal: controller.signal })
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

// Keep in sync with the detail strings the backend routes actually raise
// (src/app/routes/*.py). Anything unmapped falls through to a generic line
// rather than leaking a raw snake_case code to the user.
const ERROR_MESSAGES = {
  artist_not_found:        'That artist isn’t in the playlist dataset.',
  target_artist_not_found: 'That destination artist isn’t in the dataset.',
  none_of_the_artists_found: 'None of those artists are in the dataset.',
  artist_lookup_not_ready: 'The artist index is still warming up — try again in a moment.',
  track_not_found:         'That track isn’t in the playlist dataset.',
  source_track_not_found:  'That starting track isn’t in the dataset.',
  target_track_not_found:  'That destination track isn’t in the dataset.',
  source_track_not_in_index: 'That track isn’t in the similarity index (it covers the ~10K most-playlisted tracks).',
  target_not_in_index:     'The destination isn’t in the similarity index (~10K most-playlisted tracks).',
  no_path_found:           'No playlist path connects these two artists.',
  term_not_found:          'That word doesn’t appear in enough playlist titles.',
  title_too_short:         'Type at least two characters to search.',
  not_found:               'No result for that query.',
  no_tracks_found_for_era: 'No tracks found for that era.',
  era_tracks_not_ready:    'That era’s data is still loading — try again shortly.',
  not_ready:               'The data is still loading — give it a moment.',
  vector_index_not_ready:  'Similarity search is warming up — try again shortly.',
  server_busy:             'The demo is handling another large query. Try again in a few seconds.',
  request_timeout:         'The free demo host is still waking up. Give it one more try.',
  network_error:           'The atlas is temporarily unreachable. Check your connection and retry.',
}

export function errorMessage(error) {
  const detail = error?.detail || error?.message
  if (typeof detail !== 'string') return 'The atlas couldn’t complete this request.'
  return ERROR_MESSAGES[detail] || detail || 'The atlas couldn’t complete this request.'
}

// Warm the free host on app load so the first real query isn't a cold start.
export function warmBackend() {
  return fetch(apiUrl('/ready')).catch(() => null)
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
