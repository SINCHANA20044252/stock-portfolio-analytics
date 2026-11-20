import { useEffect, useState } from 'react'
import { api } from '../api'

// Debounced search by company name or ticker. Calls onPick({symbol, name, sector}).
export default function SymbolSearch({ onPick, placeholder = 'Search company or ticker (e.g. Infosys)' }) {
  const [q, setQ] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (q.trim().length < 2) { setRes(null); setErr(''); return }
    setBusy(true)
    const t = setTimeout(() => {
      api.search(q.trim()).then((r) => { setRes(r.results); setErr('') }).catch((e) => { setRes(null); setErr(e.message) }).finally(() => setBusy(false))
    }, 400)
    return () => clearTimeout(t)
  }, [q])

  return (
    <div className="search">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label="Search stocks" />
      {busy && <span className="muted small-text">Searching…</span>}
      {err && <span className="bad small-text">{err}</span>}
      {res && res.length === 0 && !busy && <span className="muted small-text">No matches. You can still type the symbol yourself.</span>}
      {res && res.length > 0 && (
        <ul className="results">
          {res.map((r) => (
            <li key={r.symbol}><button type="button" onClick={() => { onPick({ symbol: r.symbol, name: r.name, sector: r.sector }); setQ(''); setRes(null) }}>
              <b>{r.symbol}</b> <span>{r.name}</span> <span className="muted small-text">{r.exchange}{r.sector ? ` · ${r.sector}` : ''}</span>
            </button></li>
          ))}
        </ul>
      )}
    </div>
  )
}
