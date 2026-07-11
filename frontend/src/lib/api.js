const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')

export function apiUrl(url) {
  if (!API_BASE || /^https?:\/\//.test(url)) return url
  return `${API_BASE}${url.startsWith('/') ? url : `/${url}`}`
}

export async function getJson(url, options) {
  const res = await fetch(apiUrl(url), options)
  if (res.ok) return res.json()

  let detail = ''
  try {
    const body = await res.json()
    detail = body.detail || body.message || ''
  } catch {
    // Ignore non-JSON error bodies.
  }
  throw new Error(detail || `HTTP ${res.status}`)
}

export function errorMessage(error) {
  return error?.message || String(error || 'Unknown error')
}
