// All calls to the FastAPI backend live here.
// Login is a httpOnly cookie, so no token is ever stored in JavaScript or localStorage.
import { buildQuery, errorMessage } from './lib/query.js'

const BASE = import.meta.env.VITE_API_URL || '/api'
let onSessionLost = () => {}
export const setSessionLostHandler = (fn) => { onSessionLost = fn }

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

async function raw(path, options = {}, isForm = false) {
  const headers = { 'X-CSRF-Protection': '1', ...(isForm ? {} : { 'Content-Type': 'application/json' }) }
  return fetch(BASE + path, { credentials: 'same-origin', ...options, headers })
}

let refreshing = null
async function refreshSession() {
  refreshing = refreshing || raw('/auth/refresh', { method: 'POST' }).then((r) => r.ok).finally(() => { refreshing = null })
  return refreshing
}

async function request(path, options = {}, { isForm = false, blob = false, auth = true } = {}) {
  let res
  try {
    res = await raw(path, options, isForm)
  } catch {
    throw new ApiError('Cannot reach the server. Check that the backend is running.', 0)
  }
  if (res.status === 401 && auth) {
    if (await refreshSession()) res = await raw(path, options, isForm)
    if (res.status === 401) { onSessionLost(); throw new ApiError('Your session has expired. Please log in again.', 401) }
  }
  if (!res.ok) {
    let data = null
    try { data = await res.json() } catch { /* not JSON */ }
    throw new ApiError(errorMessage(data, `Request failed (${res.status})`), res.status)
  }
  if (blob) return res.blob()
  return res.status === 204 ? null : res.json()
}

const json = (method, body) => ({ method, body: JSON.stringify(body) })

export async function download(path, filename) {
  const blob = await request(path, {}, { blob: true })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(url)
}

export const api = {
  // auth
  register: (email, password) => request('/auth/register', json('POST', { email, password }), { auth: false }),
  login: (email, password) => request('/auth/login', json('POST', { email, password }), { auth: false }),
  logout: () => request('/auth/logout', { method: 'POST' }, { auth: false }),
  me: () => request('/auth/me'),
  updateMe: (display_name) => request('/auth/me', json('PUT', { display_name })),
  changePassword: (current_password, new_password) => request('/auth/change-password', json('POST', { current_password, new_password })),
  // portfolio
  summary: () => request('/portfolio/summary'),
  performance: (period = 'ALL') => request('/portfolio/performance' + buildQuery({ period })),
  risk: () => request('/portfolio/risk'),
  // transactions
  transactions: (filters) => request('/transactions' + buildQuery(filters)),
  addTransaction: (t) => request('/transactions', json('POST', t)),
  updateTransaction: (id, t) => request(`/transactions/${id}`, json('PUT', t)),
  deleteTransaction: (id) => request(`/transactions/${id}?confirm=true`, { method: 'DELETE' }),
  patchPosition: (id, body) => request(`/positions/${id}`, json('PATCH', body)),
  // market
  marketStatus: () => request('/market/status'),
  search: (q) => request('/market/search' + buildQuery({ q })),
  refreshPrices: () => request('/market/refresh', { method: 'POST' }),
  // goals
  plan: (g) => request('/goal/plan', json('POST', g)),
  compare: (c) => request('/goal/compare', json('POST', c)),
  goals: () => request('/goals'),
  saveGoal: (g) => request('/goals', json('POST', g)),
  updateGoal: (id, g) => request(`/goals/${id}`, json('PUT', g)),
  deleteGoal: (id) => request(`/goals/${id}`, { method: 'DELETE' }),
  // assistant, data, settings
  ask: (question) => request('/assistant/ask', json('POST', { question })),
  previewImport: (file) => { const f = new FormData(); f.append('file', file); return request('/data/import/preview', { method: 'POST', body: f }, { isForm: true }) },
  confirmImport: (id, import_valid_only) => request(`/data/import/${id}/confirm`, json('POST', { import_valid_only })),
  cancelImport: (id) => request(`/data/import/${id}`, { method: 'DELETE' }),
  preferences: () => request('/settings/preferences'),
  savePreferences: (p) => request('/settings/preferences', json('PUT', p)),
  audit: () => request('/audit'),
}
