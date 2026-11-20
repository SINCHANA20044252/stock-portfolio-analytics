// Build "?a=1&b=2" from an object, skipping empty values.
export function buildQuery(params) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  }
  const s = q.toString()
  return s ? '?' + s : ''
}

// FastAPI returns {detail: "text"} or {detail: [{loc, msg}, ...]} for validation errors.
export function errorMessage(data, fallback = 'Something went wrong') {
  const d = data && data.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d.length) {
    return d.map((e) => `${(e.loc || []).filter((x) => x !== 'body').join(' ')}: ${String(e.msg || '').replace(/^Value error, /, '')}`).join('; ')
  }
  return fallback
}
