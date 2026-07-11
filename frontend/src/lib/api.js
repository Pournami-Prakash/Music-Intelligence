export async function getJson(url, options) {
  const res = await fetch(url, options)
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
