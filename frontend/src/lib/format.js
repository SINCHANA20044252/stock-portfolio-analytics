// Pure formatting helpers (no React) so they can be unit tested with `npm test`.
export function inr(n, digits = 0) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—'
  const v = Number(n)
  const s = Math.abs(v).toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
  return (v < 0 ? '-₹' : '₹') + s
}

export function pct(n, digits = 2, signed = false) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—'
  const v = Number(n)
  return (signed && v > 0 ? '+' : '') + v.toFixed(digits) + '%'
}

// 1,50,00,000 -> "1.5Cr", 2,50,000 -> "2.5L", 12,000 -> "12K"
export function compact(n) {
  const v = Math.abs(Number(n))
  const sign = Number(n) < 0 ? '-' : ''
  if (v >= 1e7) return sign + trim(v / 1e7) + 'Cr'
  if (v >= 1e5) return sign + trim(v / 1e5) + 'L'
  if (v >= 1e3) return sign + trim(v / 1e3) + 'K'
  return sign + trim(v)
}
const trim = (x) => String(Math.round(x * 10) / 10)

export function tone(n) {
  if (n === null || n === undefined || Number(n) === 0) return ''
  return Number(n) > 0 ? 'good' : 'bad'
}

// "2025-03-07" -> "7 Mar 2025" (parsed as a plain date, no timezone shift)
export function shortDate(iso) {
  if (!iso) return '—'
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number)
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${d} ${months[m - 1]} ${y}`
}

export function timeAgo(iso, now = Date.now()) {
  if (!iso) return 'never'
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

export const todayISO = (d = new Date()) => {
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
