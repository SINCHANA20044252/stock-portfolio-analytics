import { useState } from 'react'
import { api } from '../api'
import TransactionForm from '../components/TransactionForm'
import RefreshBar from '../components/RefreshBar'
import { EmptyState, ErrorState, PageSkeleton, Card, useAsync } from '../components/ui'
import { useToast } from '../context/AppContext'
import { inr, pct, tone } from '../lib/format'
import { nextSort, sortRows } from '../lib/sort'

const COLS = [
  { key: 'symbol', label: 'Stock', get: (h) => h.symbol },
  { key: 'sector', label: 'Sector', get: (h) => h.sector },
  { key: 'quantity', label: 'Qty', get: (h) => h.quantity, num: true },
  { key: 'avg_cost', label: 'Avg cost', get: (h) => h.avg_cost, num: true },
  { key: 'current_price', label: 'Price', get: (h) => h.current_price, num: true },
  { key: 'day', label: 'Day', get: (h) => h.day_change_pct, num: true },
  { key: 'market_value', label: 'Value', get: (h) => h.market_value, num: true },
  { key: 'unrealized_pnl', label: 'Unrealized P&L', get: (h) => h.unrealized_pnl, num: true },
  { key: 'weight', label: 'Weight', get: (h) => h.weight, num: true },
]
const SOURCE = { market: 'live', manual: 'manual', transaction: 'last trade (estimate)' }

export default function Holdings({ changed }) {
  const toast = useToast()
  const { data, error, loading, reload } = useAsync(() => api.summary(), [])
  const [sort, setSort] = useState({ key: 'market_value', dir: -1 })
  const [editing, setEditing] = useState(null)
  const [adding, setAdding] = useState(false)

  if (loading && !data) return <PageSkeleton />
  if (error) return <ErrorState message={error} onRetry={reload} />
  const col = COLS.find((c) => c.key === sort.key)
  const rows = sortRows(data.holdings, col.get, sort.dir)
  const sectorOf = Object.fromEntries(data.holdings.map((h) => [h.symbol, h.sector]))

  async function savePrice(h, value) {
    setEditing(null)
    const price = Number(value)
    if (!price || price <= 0 || price === h.current_price) return
    try { await api.patchPosition(h.id, { current_price: price }); toast.success(`${h.symbol} price set manually`); reload(); changed?.() }
    catch (e) { toast.error(e.message) }
  }

  return (
    <>
      <RefreshBar asOf={data.prices_as_of} onRefreshed={reload} />
      <Card title="Your holdings" subtitle="Click a column to sort. Click a price to set it by hand."
        actions={<button className="btn primary" onClick={() => setAdding(true)}>+ Add transaction</button>}>
        {rows.length === 0 ? <EmptyState title="Nothing held right now">Add a buy to see it here.</EmptyState> : (
          <div className="table-wrap">
            <table>
              <thead><tr>{COLS.map((c) => (
                <th key={c.key} className={c.num ? 'num' : ''} aria-sort={sort.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                  <button className="th" onClick={() => setSort(nextSort(sort, c.key))}>{c.label}{sort.key === c.key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}</button>
                </th>))}</tr></thead>
              <tbody>
                {rows.map((h) => (
                  <tr key={h.symbol}>
                    <td><b>{h.symbol}</b><div className="muted small-text">{h.company_name !== h.symbol ? h.company_name : ''}</div></td>
                    <td><span className="chip">{h.sector}</span></td>
                    <td className="num">{h.quantity}</td>
                    <td className="num">{inr(h.avg_cost, 2)}</td>
                    <td className="num">
                      {editing === h.symbol ? (
                        <input className="inline" type="number" step="any" min="0" defaultValue={h.current_price ?? ''} autoFocus
                          onBlur={(e) => savePrice(h, e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); if (e.key === 'Escape') setEditing(null) }} />
                      ) : (
                        <button className="price-btn" onClick={() => setEditing(h.symbol)} title="Click to edit">{h.current_price == null ? 'Set price' : inr(h.current_price, 2)}</button>
                      )}
                      <div className="muted small-text">{SOURCE[h.price_source] || ''}</div>
                    </td>
                    <td className={`num ${tone(h.day_change_pct)}`}>{h.day_change_pct == null ? '—' : pct(h.day_change_pct, 2, true)}</td>
                    <td className="num">{inr(h.market_value)}</td>
                    <td className={`num ${tone(h.unrealized_pnl)}`}>{inr(h.unrealized_pnl)}<div className="small-text">{pct(h.unrealized_pct, 1, true)}</div></td>
                    <td className="num">{h.weight == null ? '—' : pct(h.weight, 1)}</td>
                  </tr>))}
              </tbody>
            </table>
          </div>)}
      </Card>
      {adding && <TransactionForm sectorOf={sectorOf} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload(); changed?.() }} />}
    </>
  )
}
